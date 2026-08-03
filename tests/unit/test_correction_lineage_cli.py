"""Tests for correction-lineage inspection from live pipeline artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle import correction_lineage_cli as cli


def _write_live_artifacts(tmp_path: Path) -> Path:
    decision_directory = tmp_path / "쿠쿠" / "decision-intelligence" / "snapshot"
    decision_directory.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ticker": "000660",
                "rcept_no": "20260701000001",
                "receipt_date": "2026-07-01",
                "report_name": "주요사항보고서(유상증자결정)",
                "is_correction": "False",
                "correction_parent_rcept_no": None,
                "correction_chain_root_rcept_no": "20260701000001",
                "correction_chain_order": 0,
                "correction_lineage_status": "original",
                "is_latest_in_correction_chain": False,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260706000002",
                "receipt_date": "2026-07-06",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "is_correction": "True",
                "correction_parent_rcept_no": "20260701000001",
                "correction_chain_root_rcept_no": "20260701000001",
                "correction_chain_order": 1,
                "correction_lineage_status": "linked_correction",
                "is_latest_in_correction_chain": False,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260710000003",
                "receipt_date": "2026-07-10",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "is_correction": True,
                "correction_parent_rcept_no": "20260706000002",
                "correction_chain_root_rcept_no": "20260701000001",
                "correction_chain_order": 2,
                "correction_lineage_status": "linked_correction",
                "is_latest_in_correction_chain": True,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260730000004",
                "receipt_date": "2026-07-30",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "is_correction": "1",
                "correction_parent_rcept_no": None,
                "correction_chain_root_rcept_no": "20260730000004",
                "correction_chain_order": 1,
                "correction_lineage_status": "orphan_correction",
                "is_latest_in_correction_chain": "True",
            },
        ]
    ).to_csv(decision_directory / "disclosure_events.csv", index=False)

    status_path = tmp_path / "latest_run.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "decision_directory": str(decision_directory),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return status_path


def test_load_correction_lineage_handles_utf8_korean_paths(tmp_path: Path) -> None:
    status_path = _write_live_artifacts(tmp_path)

    frame, source = cli.load_correction_lineage(status_path)

    assert source.parent.name == "snapshot"
    assert "쿠쿠" in str(source)
    assert len(frame) == 3
    assert frame.iloc[0]["correction_parent_rcept_no"] == "20260701000001"
    assert frame.iloc[-1]["ticker"] == "005930"


def test_load_correction_lineage_filters_ticker_and_latest(tmp_path: Path) -> None:
    status_path = _write_live_artifacts(tmp_path)

    frame, _ = cli.load_correction_lineage(
        status_path,
        ticker="660",
        only_latest=True,
    )

    assert len(frame) == 1
    assert frame.iloc[0]["ticker"] == "000660"
    assert frame.iloc[0]["correction_chain_order"] == 2


def test_main_prints_korean_lineage_without_manual_path_join(
    tmp_path: Path,
    capsys: object,
) -> None:
    status_path = _write_live_artifacts(tmp_path)

    result = cli.main(["--status", str(status_path), "--ticker", "005930"])

    assert result == 0
    captured = capsys.readouterr()
    assert "Correction disclosures: 1" in captured.out
    assert "[기재정정]연결재무제표기준영업" in captured.out
    assert "disclosure_events.csv" in captured.out


def test_main_reports_missing_decision_directory(
    tmp_path: Path,
    capsys: object,
) -> None:
    status_path = tmp_path / "latest_run.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "completed",
                "decision_directory": str(tmp_path / "missing"),
            }
        ),
        encoding="utf-8",
    )

    result = cli.main(["--status", str(status_path)])

    assert result == 2
    captured = capsys.readouterr()
    assert "Decision directory does not exist" in captured.err
