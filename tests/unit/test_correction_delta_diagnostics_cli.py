"""Tests for correction-delta diagnostics from persisted decision artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle.correction_delta_diagnostics_cli import (
    load_correction_delta_diagnostics,
    main,
)


def _write_latest_run(tmp_path: Path) -> Path:
    decision = tmp_path / "decision"
    decision.mkdir()
    catalysts = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "receipt_date": "2026-07-30",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "20260730800001",
                "is_correction": True,
                "document_evidence_status": "collected",
                "body_metrics_status": "verified",
                "body_metrics_type": "earnings_preliminary",
                "correction_delta_status": "parent_body_unavailable",
                "correction_delta_json": json.dumps(
                    {
                        "schema_version": 1,
                        "status": "parent_body_unavailable",
                        "metric_type": "earnings_preliminary",
                        "parent_rcept_no": "20260707800001",
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "ticker": "005930",
                "receipt_date": "2026-04-30",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "rcept_no": "20260430800001",
                "is_correction": True,
                "document_evidence_status": "collected",
                "body_metrics_status": "verified",
                "body_metrics_type": "earnings_preliminary",
                "correction_delta_status": "value_mismatch",
                "correction_delta_json": json.dumps(
                    {
                        "schema_version": 1,
                        "status": "value_mismatch",
                        "verified_field_count": 2,
                        "changed_field_count": 2,
                        "fields": [
                            {
                                "field": "sales",
                                "before_matches_parent": True,
                                "after_matches_current": True,
                            },
                            {
                                "field": "operating_profit",
                                "before_matches_parent": False,
                                "after_matches_current": True,
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "ticker": "000660",
                "receipt_date": "2026-08-07",
                "report_name": "신규시설투자등",
                "rcept_no": "20260807800001",
                "is_correction": False,
                "document_evidence_status": "collected",
                "body_metrics_status": "verified",
                "body_metrics_type": "facility_investment",
                "correction_delta_status": "not_applicable",
                "correction_delta_json": "",
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260730800001",
                "correction_lineage_status": "orphan_correction",
                "correction_chain_order": 1,
                "correction_parent_rcept_no": "",
            },
            {
                "ticker": "005930",
                "rcept_no": "20260430800001",
                "correction_lineage_status": "linked_correction",
                "correction_chain_order": 1,
                "correction_parent_rcept_no": "20260407800001",
            },
            {
                "ticker": "000660",
                "rcept_no": "20260807800001",
                "correction_lineage_status": "original",
                "correction_chain_order": 0,
                "correction_parent_rcept_no": "",
            },
        ]
    )
    catalysts.to_csv(decision / "catalysts.csv", index=False)
    events.to_csv(decision / "disclosure_events.csv", index=False)
    status = tmp_path / "latest_run.json"
    status.write_text(
        json.dumps(
            {
                "status": "completed",
                "decision_directory": str(decision.resolve()),
            }
        ),
        encoding="utf-8",
    )
    return status


def test_diagnostics_join_lineage_and_expose_delta_failure_details(tmp_path: Path) -> None:
    status = _write_latest_run(tmp_path)

    frame, summary, catalysts_path, events_path = load_correction_delta_diagnostics(status)

    assert catalysts_path.name == "catalysts.csv"
    assert events_path.name == "disclosure_events.csv"
    assert len(frame) == 2
    assert set(summary["correction_delta_status"]) == {
        "parent_body_unavailable",
        "value_mismatch",
    }
    latest = frame.loc[frame["rcept_no"] == "20260730800001"].iloc[0]
    assert latest["correction_lineage_status"] == "orphan_correction"
    assert pd.isna(latest["lineage_parent_rcept_no"]) or latest["lineage_parent_rcept_no"] == ""
    mismatch = frame.loc[frame["rcept_no"] == "20260430800001"].iloc[0]
    assert mismatch["correction_lineage_status"] == "linked_correction"
    assert mismatch["lineage_parent_rcept_no"] == "20260407800001"
    assert mismatch["verified_field_count"] == 2
    assert mismatch["changed_field_count"] == 2
    assert mismatch["mismatch_fields"] == "operating_profit(before!=parent)"


def test_diagnostics_ticker_filter_and_main_output(tmp_path: Path, capsys: object) -> None:
    status = _write_latest_run(tmp_path)

    frame, summary, _, _ = load_correction_delta_diagnostics(status, ticker="5930")

    assert len(frame) == 2
    assert set(frame["ticker"]) == {"005930"}
    assert int(summary["count"].sum()) == 2
    exit_code = main(["--status", str(status), "--ticker", "005930"])
    assert exit_code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Status summary" in captured.out
    assert "parent_body_unavailable" in captured.out
    assert "value_mismatch" in captured.out
    assert "orphan_correction" in captured.out
