"""Tests for fail-closed verification of local live-research artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.live_verify_cli import main, verify_latest_run

_REQUIRED_CSV_FILES = (
    "financial_kpis.csv",
    "financial_kpi_mapping.csv",
    "disclosure_events.csv",
    "disclosure_summary.csv",
    "macro_regime.csv",
    "market_context.csv",
    "valuation_metrics.csv",
    "financial_history.csv",
)


def _write_artifacts(tmp_path: Path, *, latest: bool = True) -> Path:
    decision = tmp_path / "쿠쿠" / "decision-intelligence" / "snapshot"
    decision.mkdir(parents=True)
    snapshot_id = "a" * 64
    warnings = ["consensus_not_available"]

    for name in _REQUIRED_CSV_FILES:
        pd.DataFrame([{"placeholder": 1}]).to_csv(decision / name, index=False)

    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260730800078",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": "2026-07-30",
                "category": "earnings",
                "priority": "high",
                "is_correction": True,
                "is_material_correction": True,
                "correction_chain_root_rcept_no": "20260730800077",
                "is_latest_in_correction_chain": latest,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260729000001",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": "2026-07-29",
                "category": "earnings",
                "priority": "high",
                "is_correction": False,
                "is_material_correction": False,
                "correction_chain_root_rcept_no": "20260729000001",
                "is_latest_in_correction_chain": True,
            },
        ]
    ).to_csv(decision / "catalysts.csv", index=False)

    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "decision_state": "positive_setup",
                "valuation_score": None,
            },
            {
                "ticker": "000660",
                "decision_state": "positive_setup",
                "valuation_score": None,
            },
        ]
    ).to_csv(decision / "scorecards.csv", index=False)
    pd.DataFrame(
        [
            {"ticker": "005930", "decision_state": "positive_setup"},
            {"ticker": "000660", "decision_state": "positive_setup"},
        ]
    ).to_csv(decision / "decision_records.csv", index=False)

    report_path = decision / "report.md"
    report_path.write_text(
        "# Alpha Cycle\n\n## 005930\n\n## 000660\n",
        encoding="utf-8",
    )
    manifest = {
        "snapshot_id": snapshot_id,
        "evaluation_date": "2026-08-03",
        "warnings": warnings,
    }
    (decision / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    status_path = tmp_path / "latest_run.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "decision_snapshot_id": snapshot_id,
                "evaluation_date": "2026-08-03",
                "decision_directory": str(decision),
                "decision_symbols": ["005930", "000660"],
                "decision_states": {"positive_setup": 2},
                "valuation_scored_count": 0,
                "report_path": str(report_path),
                "warnings": warnings,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return status_path


def test_verify_latest_run_passes_with_korean_local_path(tmp_path: Path) -> None:
    status_path = _write_artifacts(tmp_path)

    report = verify_latest_run(status_path)

    assert report.status == "passed"
    assert report.failures == ()
    assert report.checks_passed >= 15
    assert "쿠쿠" in str(report.decision_directory)


def test_verify_latest_run_fails_when_superseded_catalyst_remains(
    tmp_path: Path,
) -> None:
    status_path = _write_artifacts(tmp_path, latest=False)

    report = verify_latest_run(status_path)

    assert report.status == "failed"
    assert "superseded disclosure remains in catalysts" in report.failures


def test_main_writes_concise_verification_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status_path = _write_artifacts(tmp_path)
    output = tmp_path / "verification.json"

    result = main(["--status", str(status_path), "--output", str(output)])

    assert result == 0
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert "LIVE VERIFICATION: PASS" in capsys.readouterr().out
