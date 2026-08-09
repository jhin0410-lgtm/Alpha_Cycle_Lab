"""Tests for KOSIS parameter-data ingestion and revision-sensitive artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.kosis_industry_parameter_cli import (
    build_parameter_inventory,
    capture_parameter_data,
)
from alpha_cycle.providers.kosis import (
    DEFAULT_INDUSTRY_SEARCH,
    DEFAULT_KOSIS_TABLE_ID,
    KosisCredentials,
    KosisParameterQuery,
    KosisParameterRow,
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


def _parameter_row(
    *,
    classification_id: str = "A001",
    classification_name: str = "반도체",
    item_id: str = "T001",
    item_name: str = "생산량",
    unit_id: str = "U001",
    unit_name: str = "톤",
    period: str = "202606",
    value: str = "123.4",
    table_id: str = DEFAULT_KOSIS_TABLE_ID,
    table_name: str = DEFAULT_INDUSTRY_SEARCH,
) -> dict[str, str]:
    return {
        "ORG_ID": "101",
        "TBL_ID": table_id,
        "TBL_NM": table_name,
        "C1": classification_id,
        "C1_OBJ_NM": "품목",
        "C1_NM": classification_name,
        "ITM_ID": item_id,
        "ITM_NM": item_name,
        "UNIT_ID": unit_id,
        "UNIT_NM": unit_name,
        "PRD_SE": "M",
        "PRD_DE": period,
        "DT": value,
        "LST_CHN_DE": "20260731",
    }


def test_parameter_query_requires_coherent_time_window() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        KosisParameterQuery(start_period="202501", latest_count=None)
    with pytest.raises(ValueError, match="mutually exclusive"):
        KosisParameterQuery(
            start_period="202501",
            end_period="202506",
            latest_count=1,
        )
    with pytest.raises(ValueError, match="invalid month"):
        KosisParameterQuery(
            start_period="202513",
            end_period="202601",
            latest_count=None,
        )


def test_fetch_parameter_data_uses_official_parameter_contract() -> None:
    transport = FakeTransport([_json_response([_parameter_row()])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )
    query = KosisParameterQuery()

    rows, raw = client.fetch_parameter_data(query)

    assert len(rows) == 1
    assert rows[0].classification_ids == ("A001",)
    assert rows[0].item_id == "T001"
    assert rows[0].last_changed == "20260731"
    assert raw == [_parameter_row()]
    assert len(transport.urls) == 1
    url = transport.urls[0]
    assert url.startswith("https://kosis.kr/openapi/Param/statisticsParameterData.do?")
    assert "orgId=101" in url
    assert f"tblId={DEFAULT_KOSIS_TABLE_ID}" in url
    assert "objL1=ALL" in url
    assert "itmId=ALL" in url
    assert "prdSe=M" in url
    assert "newEstPrdCnt=1" in url
    assert "jsonVD=Y" in url


def test_fetch_parameter_data_rejects_mixed_source_identity() -> None:
    bad = {**_parameter_row(), "ORG_ID": "999"}
    transport = FakeTransport([_json_response([bad])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="mixed source identity"):
        client.fetch_parameter_data(KosisParameterQuery())


def test_fetch_parameter_data_rejects_duplicate_observation_keys() -> None:
    row = _parameter_row()
    transport = FakeTransport([_json_response([row, row])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="duplicate observation keys"):
        client.fetch_parameter_data(KosisParameterQuery())


def test_inventory_keeps_unit_variants_per_item() -> None:
    rows = tuple(
        KosisParameterRow.from_row(row)
        for row in (
            _parameter_row(unit_id="", unit_name="m3"),
            _parameter_row(
                classification_id="A002",
                classification_name="다른 품목",
                unit_id="",
                unit_name="톤",
                value="7",
            ),
        )
    )

    inventory = build_parameter_inventory(rows)

    assert inventory["item_count"] == 1
    items = inventory["items"]
    assert isinstance(items, list)
    item = items[0]
    assert item["unit_variant_count"] == 2
    assert item["units"] == [
        {"unit_id": "", "unit_name": "m3"},
        {"unit_id": "", "unit_name": "톤"},
    ]


def test_capture_writes_revision_sensitive_non_scoring_artifact(tmp_path: Path) -> None:
    transport = FakeTransport(
        [
            _json_response(
                [
                    _parameter_row(),
                    _parameter_row(
                        item_id="T002",
                        item_name="출하량",
                        value="117.0",
                    ),
                ]
            )
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = capture_parameter_data(
        client=client,
        query=KosisParameterQuery(),
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 11, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "parameter_data_captured"
    assert pointer["query_scope"] == "parameter_inventory_probe"
    assert pointer["row_count"] == 2
    assert pointer["item_count"] == 2
    assert pointer["revision_sensitive"] is True
    assert pointer["historical_vintage_certified"] is False
    assert pointer["industry_cycle_certified"] is False
    assert pointer["decision_score_enabled"] is False

    manifest_path = Path(str(pointer["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = json.loads(
        (manifest_path.parent / "parameter_inventory.json").read_text(encoding="utf-8")
    )
    assert manifest["raw_sha256"]
    assert manifest["normalized_sha256"]
    assert inventory["inventory_schema_version"] == 2
    assert inventory["classification_count"] == 1
    assert inventory["item_count"] == 2
    assert inventory["source_change_dates"] == ["20260731"]
    assert (manifest_path.parent / "raw_parameter_data.json").is_file()
    assert (manifest_path.parent / "normalized_rows.json").is_file()
    assert (tmp_path / "latest_kosis_industry_parameters.json").is_file()


def test_capture_supports_another_exact_verified_table(tmp_path: Path) -> None:
    title = "시도/산업별 광공업생산지수(2020=100)"
    table_id = "DT_INDEX"
    transport = FakeTransport(
        [_json_response([_parameter_row(table_id=table_id, table_name=title)])]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = capture_parameter_data(
        client=client,
        query=KosisParameterQuery(table_id=table_id),
        expected_table_name=title,
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 11, 0, tzinfo=UTC),
    )

    assert pointer["table_id"] == table_id
    assert pointer["table_name"] == title


def test_parameter_latest_pointer_is_ascii_safe(tmp_path: Path) -> None:
    output_root = tmp_path / "쿠쿠"
    transport = FakeTransport([_json_response([_parameter_row()])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = capture_parameter_data(
        client=client,
        query=KosisParameterQuery(),
        output_root=output_root,
        now=datetime(2026, 8, 9, 11, 0, tzinfo=UTC),
    )

    pointer_bytes = (output_root / "latest_kosis_industry_parameters.json").read_bytes()
    assert pointer_bytes.isascii()
    decoded = json.loads(pointer_bytes.decode("ascii"))
    assert decoded["artifact_directory"] == pointer["artifact_directory"]


def test_capture_rejects_unverified_table_title(tmp_path: Path) -> None:
    transport = FakeTransport([_json_response([_parameter_row(table_name="다른 통계표")])])
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="verified table"):
        capture_parameter_data(
            client=client,
            query=KosisParameterQuery(),
            output_root=tmp_path,
            now=datetime(2026, 8, 9, 11, 0, tzinfo=UTC),
        )
