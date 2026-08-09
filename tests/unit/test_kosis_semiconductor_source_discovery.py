"""Tests for semiconductor-oriented KOSIS source discovery and inventory probes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from alpha_cycle.kosis_semiconductor_source_discovery_cli import (
    CAPACITY_UTILIZATION_TABLE_NAME,
    INDUSTRY_INDEX_TABLE_NAME,
    discover_semiconductor_sources,
)
from alpha_cycle.providers.kosis import KosisCredentials, KosisReadOnlyClient
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


def _search_row(*, table_id: str, table_name: str) -> dict[str, str]:
    return {
        "ORG_ID": "101",
        "ORG_NM": "국가데이터처",
        "TBL_ID": table_id,
        "TBL_NM": table_name,
        "STAT_ID": "1970002",
        "STAT_NM": "광업제조업동향조사",
        "VW_CD": "MT_ZTITLE",
        "MT_ATITLE": "광업·제조업 > 광업제조업동향조사",
        "STRT_PRD_DE": "200001",
        "END_PRD_DE": "202606",
    }


def _parameter_row(
    *,
    table_id: str,
    table_name: str,
    item_id: str,
    item_name: str,
    industry_name: str = "반도체 제조업",
) -> dict[str, str]:
    return {
        "ORG_ID": "101",
        "TBL_ID": table_id,
        "TBL_NM": table_name,
        "C1": "00",
        "C1_OBJ_NM": "시도별",
        "C1_NM": "전국",
        "C2": "C261",
        "C2_OBJ_NM": "산업별",
        "C2_NM": industry_name,
        "ITM_ID": item_id,
        "ITM_NM": item_name,
        "UNIT_ID": "IDX",
        "UNIT_NM": "2020=100",
        "PRD_SE": "M",
        "PRD_DE": "202606",
        "DT": "123.4",
        "LST_CHN_DE": "20260731",
    }


def test_discovery_verifies_both_semiconductor_source_inventories(tmp_path: Path) -> None:
    index_id = "DT_INDEX"
    capacity_id = "DT_CAPACITY"
    capacity_response_title = "제조업 생산능력 및 가동률지수"
    transport = FakeTransport(
        [
            _json_response([_search_row(table_id=index_id, table_name=INDUSTRY_INDEX_TABLE_NAME)]),
            _json_response([{"TBL_NM": INDUSTRY_INDEX_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T10",
                        item_name="생산지수",
                    ),
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T20",
                        item_name="출하지수",
                    ),
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T30",
                        item_name="재고지수",
                    ),
                ]
            ),
            _json_response(
                [_search_row(table_id=capacity_id, table_name=CAPACITY_UTILIZATION_TABLE_NAME)]
            ),
            _json_response([{"TBL_NM": CAPACITY_UTILIZATION_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=capacity_id,
                        table_name=capacity_response_title,
                        item_id="T40",
                        item_name="생산능력지수",
                    ),
                    _parameter_row(
                        table_id=capacity_id,
                        table_name=capacity_response_title,
                        item_id="T41",
                        item_name="가동률지수",
                    ),
                ]
            ),
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover_semiconductor_sources(
        client=client,
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "semiconductor_source_inventory_verified"
    assert pointer["quantity_table_primary_for_semiconductors"] is False
    assert pointer["industry_cycle_certified"] is False
    assert pointer["decision_score_enabled"] is False
    targets = pointer["targets"]
    assert isinstance(targets, list)
    assert [target["table_id"] for target in targets] == [index_id, capacity_id]
    assert all(target["status"] == "inventory_verified" for target in targets)
    assert all(target["semiconductor_classification_count"] == 1 for target in targets)
    assert targets[0]["probe_object_codes"] == ["ALL", "ALL"]
    assert targets[1]["probe_object_codes"] == ["ALL"]
    assert targets[0]["parameter_title_matches_metadata"] is True
    assert targets[1]["parameter_title_matches_metadata"] is False
    assert targets[1]["parameter_response_titles"] == [capacity_response_title]

    assert len(transport.urls) == 6
    assert sum("statisticsSearch.do" in url for url in transport.urls) == 2
    assert sum("statisticsData.do" in url for url in transport.urls) == 2
    assert sum("statisticsParameterData.do" in url for url in transport.urls) == 2
    index_params = parse_qs(urlparse(transport.urls[2]).query)
    capacity_params = parse_qs(urlparse(transport.urls[5]).query)
    assert index_params["objL1"] == ["ALL"]
    assert index_params["objL2"] == ["ALL"]
    assert capacity_params["objL1"] == ["ALL"]
    assert "objL2" not in capacity_params
    assert (tmp_path / "latest_kosis_semiconductor_source_discovery.json").is_file()


def test_discovery_stays_incomplete_without_semiconductor_classification(
    tmp_path: Path,
) -> None:
    index_id = "DT_INDEX"
    capacity_id = "DT_CAPACITY"
    transport = FakeTransport(
        [
            _json_response([_search_row(table_id=index_id, table_name=INDUSTRY_INDEX_TABLE_NAME)]),
            _json_response([{"TBL_NM": INDUSTRY_INDEX_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T10",
                        item_name="생산지수",
                        industry_name="자동차 제조업",
                    )
                ]
            ),
            _json_response(
                [_search_row(table_id=capacity_id, table_name=CAPACITY_UTILIZATION_TABLE_NAME)]
            ),
            _json_response([{"TBL_NM": CAPACITY_UTILIZATION_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=capacity_id,
                        table_name="제조업 생산능력 및 가동률지수",
                        item_id="T41",
                        item_name="가동률지수",
                    )
                ]
            ),
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover_semiconductor_sources(
        client=client,
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "semiconductor_source_discovery_incomplete"
    targets = pointer["targets"]
    assert isinstance(targets, list)
    assert targets[0]["status"] == "no_semiconductor_classification"
    assert targets[1]["status"] == "inventory_verified"
    assert pointer["industry_cycle_certified"] is False


def test_discovery_rejects_inconsistent_parameter_titles(tmp_path: Path) -> None:
    index_id = "DT_INDEX"
    capacity_id = "DT_CAPACITY"
    transport = FakeTransport(
        [
            _json_response([_search_row(table_id=index_id, table_name=INDUSTRY_INDEX_TABLE_NAME)]),
            _json_response([{"TBL_NM": INDUSTRY_INDEX_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T10",
                        item_name="생산지수",
                    ),
                    _parameter_row(
                        table_id=index_id,
                        table_name="다른 제목",
                        item_id="T20",
                        item_name="출하지수",
                    ),
                ]
            ),
            _json_response(
                [_search_row(table_id=capacity_id, table_name=CAPACITY_UTILIZATION_TABLE_NAME)]
            ),
            _json_response([{"TBL_NM": CAPACITY_UTILIZATION_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=capacity_id,
                        table_name=CAPACITY_UTILIZATION_TABLE_NAME,
                        item_id="T41",
                        item_name="가동률지수",
                    )
                ]
            ),
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover_semiconductor_sources(
        client=client,
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    targets = pointer["targets"]
    assert isinstance(targets, list)
    assert targets[0]["status"] == "parameter_title_inconsistent"
    assert pointer["status"] == "semiconductor_source_discovery_incomplete"


def test_discovery_pointer_is_ascii_safe(tmp_path: Path) -> None:
    index_id = "DT_INDEX"
    capacity_id = "DT_CAPACITY"
    output_root = tmp_path / "쿠쿠"
    transport = FakeTransport(
        [
            _json_response([_search_row(table_id=index_id, table_name=INDUSTRY_INDEX_TABLE_NAME)]),
            _json_response([{"TBL_NM": INDUSTRY_INDEX_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=index_id,
                        table_name=INDUSTRY_INDEX_TABLE_NAME,
                        item_id="T10",
                        item_name="생산지수",
                    )
                ]
            ),
            _json_response(
                [_search_row(table_id=capacity_id, table_name=CAPACITY_UTILIZATION_TABLE_NAME)]
            ),
            _json_response([{"TBL_NM": CAPACITY_UTILIZATION_TABLE_NAME}]),
            _json_response(
                [
                    _parameter_row(
                        table_id=capacity_id,
                        table_name=CAPACITY_UTILIZATION_TABLE_NAME,
                        item_id="T41",
                        item_name="가동률지수",
                    )
                ]
            ),
        ]
    )
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = discover_semiconductor_sources(
        client=client,
        output_root=output_root,
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    pointer_path = output_root / "latest_kosis_semiconductor_source_discovery.json"
    pointer_bytes = pointer_path.read_bytes()
    assert pointer_bytes.isascii()
    decoded = json.loads(pointer_bytes.decode("ascii"))
    assert decoded["artifact_directory"] == pointer["artifact_directory"]