from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision_industry_evidence_calibrated import (
    _GENERIC_INDUSTRY_GAP,
    _RESIDUAL_INDUSTRY_GAP,
    _kosis_capture_date_in_korea,
    _reconcile_industry_evidence_gaps,
    _reconcile_industry_gap_report,
    _sync_record_evidence_gaps,
)


def test_kosis_capture_date_uses_korea_calendar_day(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    manifest = artifact / "manifest.json"
    manifest.write_text(
        json.dumps({"captured_at": "2026-08-09T16:30:00+00:00"}),
        encoding="utf-8",
    )
    pointer = tmp_path / "latest.json"
    pointer.write_text(
        json.dumps({"manifest_path": str(manifest.resolve())}),
        encoding="utf-8",
    )

    capture_date = _kosis_capture_date_in_korea(pointer)

    assert capture_date.isoformat() == "2026-08-10"


def test_verified_kosis_replaces_only_generic_industry_gap_with_residual_gap() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "industry_evidence_available": True,
                "evidence_gaps": json.dumps(
                    [_GENERIC_INDUSTRY_GAP, "컨센서스 미연결"],
                    ensure_ascii=False,
                ),
            },
            {
                "ticker": "035420",
                "industry_evidence_available": False,
                "evidence_gaps": json.dumps(
                    [_GENERIC_INDUSTRY_GAP],
                    ensure_ascii=False,
                ),
            },
        ]
    )

    result = _reconcile_industry_evidence_gaps(scorecards)

    hynix = json.loads(result.loc[result["ticker"] == "000660", "evidence_gaps"].iloc[0])
    unrelated = json.loads(result.loc[result["ticker"] == "035420", "evidence_gaps"].iloc[0])
    assert _GENERIC_INDUSTRY_GAP not in hynix
    assert _RESIDUAL_INDUSTRY_GAP in hynix
    assert "컨센서스 미연결" in hynix
    assert unrelated == [_GENERIC_INDUSTRY_GAP]


def test_decision_records_receive_reconciled_scorecard_gap() -> None:
    records = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "evidence_gaps": json.dumps([_GENERIC_INDUSTRY_GAP], ensure_ascii=False),
                "decision_state": "mixed_setup",
            }
        ]
    )
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "evidence_gaps": json.dumps([_RESIDUAL_INDUSTRY_GAP], ensure_ascii=False),
            }
        ]
    )

    result = _sync_record_evidence_gaps(records, scorecards)

    assert json.loads(result.loc[0, "evidence_gaps"]) == [_RESIDUAL_INDUSTRY_GAP]
    assert result.loc[0, "decision_state"] == "mixed_setup"


def test_report_replaces_generic_gap_only_for_applicable_playbook_ticker() -> None:
    report = "\n".join(
        [
            "# report",
            "",
            "## 실행 플레이북",
            "",
            "### 000660",
            "- 현재 근거 공백",
            f"  - {_GENERIC_INDUSTRY_GAP}",
            "",
            "### 035420",
            "- 현재 근거 공백",
            f"  - {_GENERIC_INDUSTRY_GAP}",
            "",
            "## 다른 섹션",
            f"- {_GENERIC_INDUSTRY_GAP}",
            "",
        ]
    )

    result = _reconcile_industry_gap_report(report, {"000660"})

    assert f"  - {_RESIDUAL_INDUSTRY_GAP}" in result
    assert result.count(_GENERIC_INDUSTRY_GAP) == 2
