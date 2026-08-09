"""Tests for verified KOSIS semiconductor history capture and diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from alpha_cycle.kosis_semiconductor_history_cli import (
    CAPACITY_TABLE_ID,
    CAPACITY_TABLE_NAME,
    HEURISTIC_SPREAD_DEADBAND_PP,
    INDEX_TABLE_ID,
    INDEX_TABLE_NAME,
    SERIES_SPECS,
    build_semiconductor_diagnostics,
    capture_semiconductor_history,
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


def _periods() -> list[str]:
    return [
        "202506",
        "202507",
        "202508",
        "202509",
        "202510",
        "202511",
        "202512",
        "202601",
        "202602",
        "202603",
        "202604",
        "202605",
        "202606",
    ]


def _series_rows(metric: str) -> list[dict[str, str]]:
    spec = next(spec for spec in SERIES_SPECS if spec.metric == metric)
    values = {period: 100.0 for period in _periods()}
    final_values = {
        "production_raw": 112.0,
        "shipment_raw": 115.0,
        "inventory_raw": 105.0,
        "capacity_raw": 110.0,
        "utilization_raw": 108.0,
        "production_sa": 112.0,
        "shipment_sa": 115.0,
        "inventory_sa": 105.0,
        "utilization_sa": 108.0,
    }
    previous_values = {
        "production_sa": 110.0,
        "shipment_sa": 112.0,
        "inventory_sa": 106.0,
        "utilization_sa": 105.0,
    }
    if metric in previous_values:
        values["202605"] = previous_values[metric]
    values["202606"] = final_values[metric]

    rows: list[dict[str, str]] = []
    for period in _periods():
        row = {
            "ORG_ID": "101",
            "TBL_ID": spec.table_id,
            "TBL_NM": spec.table_name.replace("=", "＝"),
            "ITM_ID": spec.item_id,
            "ITM_NM": spec.item_name,
            "UNIT_ID": "",
            "UNIT_NM": "2020＝100",
            "PRD_SE": "M",
            "PRD_DE": period,
            "DT": str(values[period]),
            "LST_CHN_DE": "20260731",
        }
        if len(spec.object_codes) == 2:
            row.update(
                {
                    "C1": spec.object_codes[0],
                    "C1_OBJ_NM": "시도별",
                    "C1_NM": spec.classification_names[0],
                    "C2": spec.object_codes[1],
                    "C2_OBJ_NM": "산업별",
                    "C2_NM": spec.classification_names[1],
                }
            )
        else:
            row.update(
                {
                    "C1": spec.object_codes[0],
                    "C1_OBJ_NM": "산업별",
                    "C1_NM": spec.classification_names[0],
                }
            )
        rows.append(row)
    return rows


def _transport() -> FakeTransport:
    responses = [
        _json_response([_search_row(table_id=INDEX_TABLE_ID, table_name=INDEX_TABLE_NAME)]),
        _json_response([{"TBL_NM": INDEX_TABLE_NAME}]),
        _json_response([_search_row(table_id=CAPACITY_TABLE_ID, table_name=CAPACITY_TABLE_NAME)]),
        _json_response([{"TBL_NM": CAPACITY_TABLE_NAME}]),
    ]
    responses.extend(_json_response(_series_rows(spec.metric)) for spec in SERIES_SPECS)
    return FakeTransport(responses)


def test_capture_semiconductor_history_uses_verified_bindings_and_stays_non_scoring(
    tmp_path: Path,
) -> None:
    transport = _transport()
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    pointer = capture_semiconductor_history(
        client=client,
        output_root=tmp_path,
        now=datetime(2026, 8, 9, 12, 40, tzinfo=UTC),
        months=13,
    )

    assert pointer["status"] == "semiconductor_history_captured"
    assert pointer["diagnostics_status"] == "heuristic_diagnostics_available"
    assert pointer["latest_period"] == "202606"
    assert pointer["series_count"] == 9
    assert pointer["historical_vintage_certified"] is False
    assert pointer["point_in_time_backtest_eligible"] is False
    assert pointer["heuristic_phase_certified"] is False
    assert pointer["industry_cycle_certified"] is False
    assert pointer["decision_score_enabled"] is False

    artifact_directory = Path(str(pointer["artifact_directory"]))
    diagnostics = json.loads(
        (artifact_directory / "diagnostics.json").read_text(encoding="utf-8")
    )
    latest = diagnostics["latest"]
    assert diagnostics["schema_version"] == 2
    assert diagnostics["methodology"]["heuristic_phase_spread_deadband_pp"] == pytest.approx(
        HEURISTIC_SPREAD_DEADBAND_PP
    )
    assert latest["production_yoy_pct"] == pytest.approx(12.0)
    assert latest["shipment_yoy_pct"] == pytest.approx(15.0)
    assert latest["inventory_yoy_pct"] == pytest.approx(5.0)
    assert latest["shipment_minus_inventory_yoy_pp"] == pytest.approx(10.0)
    assert latest["capacity_yoy_pct"] == pytest.approx(10.0)
    assert latest["utilization_yoy_pct"] == pytest.approx(8.0)
    assert latest["heuristic_phase"] == "expansion_inventory_controlled"
    assert "inventory_sa_mom_negative" in latest["momentum_confirmations"]

    assert len(transport.urls) == 13
    parameter_urls = [url for url in transport.urls if "statisticsParameterData.do" in url]
    assert len(parameter_urls) == 9
    parsed = [parse_qs(urlparse(url).query) for url in parameter_urls]
    assert all(query["newEstPrdCnt"] == ["13"] for query in parsed)
    index_queries = [query for query in parsed if query["tblId"] == [INDEX_TABLE_ID]]
    capacity_queries = [query for query in parsed if query["tblId"] == [CAPACITY_TABLE_ID]]
    assert all(
        query["objL1"] == ["00"] and query["objL2"] == ["C261"]
        for query in index_queries
    )
    assert all(
        query["objL1"] == ["C261"] and "objL2" not in query
        for query in capacity_queries
    )

    pointer_bytes = (tmp_path / "latest_kosis_semiconductor_history.json").read_bytes()
    assert pointer_bytes.isascii()


def test_build_semiconductor_diagnostics_labels_recovery_destocking() -> None:
    values = {
        "shipment_raw": {"202506": 100.0, "202606": 105.0},
        "inventory_raw": {"202506": 100.0, "202606": 95.0},
        "production_raw": {"202506": 100.0, "202606": 103.0},
    }

    diagnostics = build_semiconductor_diagnostics(values)

    latest = diagnostics["latest"]
    assert isinstance(latest, dict)
    assert latest["heuristic_phase"] == "recovery_destocking"
    assert latest["shipment_yoy_pct"] == pytest.approx(5.0)
    assert latest["inventory_yoy_pct"] == pytest.approx(-5.0)
    assert diagnostics["industry_cycle_certified"] is False
    assert diagnostics["decision_score_enabled"] is False


def test_build_semiconductor_diagnostics_uses_deadband_for_near_equal_growth() -> None:
    values = {
        "shipment_raw": {"202506": 100.0, "202606": 103.11},
        "inventory_raw": {"202506": 100.0, "202606": 103.02},
        "production_raw": {"202506": 100.0, "202606": 102.25},
    }

    diagnostics = build_semiconductor_diagnostics(values)

    latest = diagnostics["latest"]
    assert isinstance(latest, dict)
    assert latest["shipment_minus_inventory_yoy_pp"] == pytest.approx(0.09)
    assert latest["heuristic_phase"] == "expansion_inventory_balanced"


def test_build_semiconductor_diagnostics_keeps_material_inventory_build_signal() -> None:
    values = {
        "shipment_raw": {"202506": 100.0, "202606": 103.0},
        "inventory_raw": {"202506": 100.0, "202606": 105.0},
        "production_raw": {"202506": 100.0, "202606": 103.5},
    }

    diagnostics = build_semiconductor_diagnostics(values)

    latest = diagnostics["latest"]
    assert isinstance(latest, dict)
    assert latest["shipment_minus_inventory_yoy_pp"] == pytest.approx(-2.0)
    assert latest["heuristic_phase"] == "expansion_inventory_build"


def test_capture_semiconductor_history_rejects_classification_drift(tmp_path: Path) -> None:
    transport = _transport()
    bad_rows = _series_rows("production_raw")
    for row in bad_rows:
        row["C2"] = "C262"
    transport.responses[4] = _json_response(bad_rows)
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=transport,
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="classification ID drift"):
        capture_semiconductor_history(
            client=client,
            output_root=tmp_path,
            now=datetime(2026, 8, 9, 12, 40, tzinfo=UTC),
            months=13,
        )


def test_capture_semiconductor_history_requires_at_least_thirteen_months(
    tmp_path: Path,
) -> None:
    client = KosisReadOnlyClient(
        KosisCredentials(api_key="secret-key"),
        transport=FakeTransport([]),
        max_retries=0,
        sleep=lambda _: None,
    )

    with pytest.raises(ValueError, match="between 13 and"):
        capture_semiconductor_history(
            client=client,
            output_root=tmp_path,
            now=datetime(2026, 8, 9, 12, 40, tzinfo=UTC),
            months=12,
        )
