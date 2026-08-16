from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralRankProbeResult,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    capture_structural_rank_probe_report,
    load_structural_rank_probe_report,
)


def _result() -> StructuralRankProbeResult:
    return StructuralRankProbeResult(
        evidence_id="1" * 64,
        evaluation_date=date(2026, 8, 16),
        method_id="skhynix_aggregate_direction_rank_probe",
        method_version="0.1-draft",
        method_manifest_sha256="2" * 64,
        historical_product_revenue_evidence_id="3" * 64,
        company_profitability_evidence_id="4" * 64,
        cycle_driver_evidence_id="5" * 64,
        candidate_aligned_periods=(),
        training_periods=(),
        holdout_excluded_periods=(),
        reconciliation_failed_periods=(),
        rows=(),
        row_count=0,
        parameter_count=7,
        design_rank=0,
        full_column_rank=False,
        normalized_condition_number=None,
        company_product_revenue_reconciliation_certified=True,
        rank_probe_ready=False,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reason="insufficient_aligned_training_rows",
    )


def test_capture_and_offline_replay_preserve_fail_closed_zero_row_probe(
    monkeypatch, tmp_path
) -> None:
    import alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report as module

    monkeypatch.setattr(module, "load_structural_rank_probe_from_pointers", lambda **kwargs: _result())
    captured = capture_structural_rank_probe_report(
        evaluation_date=date(2026, 8, 16),
        method_path=tmp_path / "method.yaml",
        historical_product_revenue_pointer=tmp_path / "historical.json",
        company_profitability_pointer=tmp_path / "company.json",
        cycle_driver_pointer=tmp_path / "cycle.json",
        output=tmp_path / "output",
        captured_at=datetime(2026, 8, 16, 11, 0, tzinfo=UTC),
    )
    pointer = tmp_path / "output" / "latest_structural_rank_probe.json"
    verified = load_structural_rank_probe_report(
        pointer,
        evaluation_date=date(2026, 8, 16),
    )
    assert verified.evidence_id == "1" * 64
    assert verified.row_count == 0
    assert verified.fit_attempt_allowed is False
    assert captured["block_reason"] == "insufficient_aligned_training_rows"


def test_offline_replay_rejects_tampered_rank_report(monkeypatch, tmp_path) -> None:
    import alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report as module

    monkeypatch.setattr(module, "load_structural_rank_probe_from_pointers", lambda **kwargs: _result())
    captured = capture_structural_rank_probe_report(
        evaluation_date=date(2026, 8, 16),
        method_path=tmp_path / "method.yaml",
        historical_product_revenue_pointer=tmp_path / "historical.json",
        company_profitability_pointer=tmp_path / "company.json",
        cycle_driver_pointer=tmp_path / "cycle.json",
        output=tmp_path / "output",
        captured_at=datetime(2026, 8, 16, 11, 0, tzinfo=UTC),
    )
    report_path = captured["report_path"]
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    report["design_rank"] = 7
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    with pytest.raises(ValueError, match="report payload"):
        load_structural_rank_probe_report(
            tmp_path / "output" / "latest_structural_rank_probe.json",
            evaluation_date=date(2026, 8, 16),
        )
