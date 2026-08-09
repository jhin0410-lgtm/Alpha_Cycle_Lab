"""Tests for the read-only KOSIS industry discovery boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.kosis_industry_discovery_cli import discover
from alpha_cycle.providers.kosis import (
    DEFAULT_INDUSTRY_SEARCH,
    KosisCredentials,
    KosisReadOnlyClient,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse


class FakeTransport:
    def __init__(self, responses: list[HttpBytesResponse]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        del headers, timeout_seconds
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("unexpected KOSIS request")
        return self.responses.pop(0)


def _json_response(value: object) -> HttpBytesResponse:
    return HttpBytesResponse(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps(value, ensure_ascii=False).encode("utf-8"),
    )


def _search_row(*, title: str = DEFAULT_INDUSTRY_SEARCH) -> dict[str, str]:
    return {
        "ORG_ID": "101",
        "ORG_NM": "국가데이터처",
        "TBL_ID": "DT_TEST_TABLE",
        "TBL_NM": title,
        "STAT_ID": "STAT_TEST",
        "STAT_NM": "광업제조업동향조사",
        "VW_CD": "MT_ZTITLE",
        "MT_ATITLE": "광업·제조업 > 광업제조업동향조사",
        "STRT_PRD_DE": "200001",
        "END_PRD_DE": "202606",
    }


def test_kosis_credentials_require_local_non_placeholder_key() -> None:
    with pytest.raises(ValueError, match="KOSIS_API_KEY"):
        KosisCredentials.from_env({})
    with pytest.raises(ValueError, match="placeholder"):
        KosisCredentials.from_env({"KOSIS_API_KEY": "replace_with_local_secret"})
    credentials = KosisCredentials.from_env({"KOSIS_API_KEY": "secret-key"})
    assert credentials.api_key == "secret-key"


def test_kosis_credentials_reject_non_official_host() -> None:
    with pytest.raises(ValueError, match="official KOSIS"):
        KosisCredentials(api_key="secret-key", base_url="https://example.com/openapi")


def test_search_tables_uses_official_integrated_search_contract() -> None:
    transport = FakeTransport([_json_response([_search_row()])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    candidates, raw = client.search_tables(DEFAULT_INDUSTRY_SEARCH, org_id="101")

    assert len(candidates) == 1
    assert candidates[0].table_id == "DT_TEST_TABLE"
    assert raw == [_search_row()]
    assert len(transport.urls) == 1
    assert transport.urls[0].startswith("https://kosis.kr/openapi/statisticsSearch.do?")
    assert "searchNm=" in transport.urls[0]
    assert "orgId=101" in transport.urls[0]
    assert "jsonVD=Y" in transport.urls[0]


def test_discover_writes_verified_non_scoring_identity(tmp_path: Path) -> None:
    transport = FakeTransport(
        [
            _json_response([_search_row()]),
            _json_response([{"TBL_NM": DEFAULT_INDUSTRY_SEARCH}]),
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover(
        client=client,
        search_name=DEFAULT_INDUSTRY_SEARCH,
        org_id="101",
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 9, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "table_identity_verified"
    assert pointer["selected_table_id"] == "DT_TEST_TABLE"
    assert pointer["industry_cycle_certified"] is False
    assert pointer["decision_score_enabled"] is False
    assert len(transport.urls) == 2
    assert all("jsonVD=Y" in url for url in transport.urls)
    manifest_path = Path(str(pointer["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["metadata_title_verified"] is True
    assert manifest["exact_match_count"] == 1
    assert manifest["industry_cycle_certified"] is False
    assert (manifest_path.parent / "raw_search.json").is_file()
    assert (manifest_path.parent / "raw_table_meta.json").is_file()
    assert (manifest_path.parent / "candidates.json").is_file()
    assert (tmp_path / "latest_kosis_industry_discovery.json").is_file()


def test_discover_keeps_ambiguous_identity_uncertified(tmp_path: Path) -> None:
    transport = FakeTransport(
        [_json_response([_search_row(), {**_search_row(), "TBL_ID": "DT_TEST_TABLE_2"}])]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover(
        client=client,
        search_name=DEFAULT_INDUSTRY_SEARCH,
        org_id="101",
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 9, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "ambiguous_exact_table_match"
    assert pointer["selected_table_id"] is None
    assert pointer["industry_cycle_certified"] is False
    assert len(transport.urls) == 1


def test_kosis_error_payload_fails_closed() -> None:
    transport = FakeTransport([_json_response({"err": "21", "errMsg": "잘못된 요청 변수"})])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="code=21"):
        client.search_tables(DEFAULT_INDUSTRY_SEARCH)
