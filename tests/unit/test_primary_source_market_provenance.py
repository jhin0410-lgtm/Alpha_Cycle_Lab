"""Tests for primary-source research when provider market scopes differ."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from alpha_cycle import pipeline_market_consistency as strict_gate
from alpha_cycle import pipeline_market_consistency_degraded as degraded_gate
from alpha_cycle.intelligence.decision_provenance import (
    build_decision_evidence_envelope,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)
from alpha_cycle.intelligence.primary_source_market_provenance import (
    load_primary_source_market_provenance,
)
from alpha_cycle.market_consistency_cli import _result_id
from alpha_cycle.market_consistency_runner_cli import _assessment_id

MARKET_ID = "b" * 64
KIWOOM_ID = "c" * 64
DECISION_ID = "d" * 64
SYMBOLS = ("000660", "005930", "005935")


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _symbol_row(ticker: str) -> dict[str, object]:
    venue_variable = ticker in {"000660", "005930"}
    return {
        "ticker": ticker,
        "scope_role": (
            "venue_variable_evidence" if venue_variable else "krx_only_control"
        ),
        "rows_compared": 20,
        "price_difference_rows": 20 if venue_variable else 0,
        "tolerance_conflict_rows": 20 if venue_variable else 0,
        "volume_difference_rows": 20 if venue_variable else 0,
        "full_series_price_difference": venue_variable,
        "full_series_volume_difference": venue_variable,
        "possible_kiwoom_symbol": None,
        "possible_symbol_match_rows": 0,
    }


def _scope_case(
    root: Path,
    *,
    comparable_conflicts: int = 0,
    control_price_differences: int = 0,
) -> tuple[Path, Path]:
    result_path = root / "market-source-consistency" / "case" / "consistency.json"
    assessment_path = result_path.parent / "market_scope_assessment.json"
    raw_payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": "failed",
        "checked_at_utc": "2026-08-05T14:00:00+00:00",
        "checked_at_kst": "2026-08-05T23:00:00+09:00",
        "expected_symbols": list(SYMBOLS),
        "toss_snapshot_id": MARKET_ID,
        "toss_captured_at": "2026-08-05T14:00:00+00:00",
        "toss_snapshot_age_seconds": 0.0,
        "toss_directory": "market",
        "toss_resolution_source": "explicit_pipeline_market_directory",
        "kiwoom_snapshot_id": KIWOOM_ID,
        "kiwoom_captured_at": "2026-08-05T13:00:00+00:00",
        "kiwoom_snapshot_age_seconds": 3600.0,
        "kiwoom_directory": "kiwoom",
        "historical_cutoff_date_exclusive": "2026-08-05",
        "historical_days_required_per_symbol": 20,
        "historical_rows_compared": 60,
        "historical_symbols_passed": ["005935"],
        "historical_price_conflict_count": 40,
        "historical_volume_mismatch_count": 40,
        "live_quote_status": "not_comparable",
        "live_quote_comparable_count": 0,
        "live_quote_conflict_count": 0,
        "live_capture_gap_seconds": 3600.0,
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "warnings": [],
        "failures": ["historical price differences"],
        "daily_comparisons_file": "daily_price_comparisons.csv",
        "quote_comparisons_file": "live_quote_comparisons.csv",
    }
    result_id = _result_id(raw_payload)
    raw_payload["result_id"] = result_id
    _write(result_path, raw_payload)

    symbol_rows = [_symbol_row(ticker) for ticker in SYMBOLS]
    if control_price_differences:
        control = next(row for row in symbol_rows if row["ticker"] == "005935")
        control["price_difference_rows"] = control_price_differences
    assessment_payload: dict[str, object] = {
        "schema_version": "1.3",
        "status": "blocked_market_scope_mismatch",
        "classification": "inferred_venue_scope_mismatch",
        "checked_at_utc": raw_payload["checked_at_utc"],
        "checked_at_kst": raw_payload["checked_at_kst"],
        "raw_result_id": result_id,
        "raw_result_path": str(result_path.resolve()),
        "raw_status": "failed",
        "raw_price_difference_count": 40,
        "tolerance_conflict_count": 40,
        "comparable_scope_price_conflict_count": comparable_conflicts,
        "scope_incompatible_row_count": 40,
        "historical_scope_status": "not_comparable",
        "toss_historical_market_scope": "provider_unspecified_domestic_scope",
        "kiwoom_historical_market_scope": "krx_opt10081",
        "scope_incompatible_symbols": ["000660", "005930"],
        "control_symbols_verified": ["005935"],
        "live_quote_status": "not_comparable",
        "live_quote_conflict_count": 0,
        "raw_failures": ["historical price differences"],
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "rationale": [
            "The two historical series are market-scope non-equivalent.",
        ],
        "symbols": symbol_rows,
    }
    assessment_id = _assessment_id(assessment_payload)
    assessment_payload["assessment_id"] = assessment_id
    _write(assessment_path, assessment_payload)

    _write(
        root / "latest_market_consistency.json",
        {
            "status": "failed",
            "result_id": result_id,
            "checked_at_utc": raw_payload["checked_at_utc"],
            "result_path": str(result_path.resolve()),
            "raw_decision_integration_eligible": False,
            "decision_integration_eligible": False,
            "assessment_status": "completed",
            "assessment_id": assessment_id,
            "assessment_path": str(assessment_path.resolve()),
            "classification": "inferred_venue_scope_mismatch",
            "assessment_failure": None,
            "historical_price_conflict_count": 40,
            "live_quote_status": "not_comparable",
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    _write(
        root / "latest_market_scope_assessment.json",
        {
            "status": "blocked_market_scope_mismatch",
            "classification": "inferred_venue_scope_mismatch",
            "assessment_id": assessment_id,
            "assessment_path": str(assessment_path.resolve()),
            "raw_result_id": result_id,
            "raw_result_path": str(result_path.resolve()),
            "decision_integration_eligible": False,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    return result_path, assessment_path


def test_strict_scope_pattern_allows_primary_source_research(tmp_path: Path) -> None:
    _scope_case(tmp_path)

    provenance = load_primary_source_market_provenance(
        tmp_path,
        market_snapshot_id=MARKET_ID,
        decision_symbols=("005930", "000660"),
    )

    assert provenance.mode == "primary_source_only"
    assert provenance.raw_status == "failed"
    assert provenance.classification == "inferred_venue_scope_mismatch"
    assert provenance.historical_verified is False
    assert provenance.live_price_certified is False
    assert provenance.decision_integration_eligible is False
    assert "primary_market_snapshot_tossinvest_only" in provenance.warnings


def test_primary_source_mode_is_explicit_in_decision_envelope(tmp_path: Path) -> None:
    _scope_case(tmp_path)
    provenance = load_primary_source_market_provenance(
        tmp_path,
        market_snapshot_id=MARKET_ID,
        decision_symbols=("005930", "000660"),
    )
    decision = tmp_path / "decision"
    _write(
        decision / "manifest.json",
        {"snapshot_id": DECISION_ID, "market_snapshot_id": MARKET_ID},
    )

    envelope = build_decision_evidence_envelope(
        decision,
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=provenance,
        now=datetime(2026, 8, 5, 15, tzinfo=UTC),
    )

    assert envelope.market_provenance_status == "primary_source_only"
    assert envelope.reference_price_cross_provider_certified is False
    assert (
        "market_consistency_primary_source_only_cross_provider_scope_not_comparable"
        in envelope.warnings
    )
    payload = envelope.identity_payload()
    assert payload["historical_market_evidence_verified"] is False
    assert payload["decision_integration_eligible"] is False
    assert payload["automatic_provider_substitution_enabled"] is False
    assert payload["order_api_enabled"] is False


@pytest.mark.parametrize(
    ("comparable_conflicts", "control_price_differences"),
    [(1, 0), (0, 1)],
)
def test_true_or_control_conflicts_still_block_primary_source_mode(
    tmp_path: Path,
    comparable_conflicts: int,
    control_price_differences: int,
) -> None:
    _scope_case(
        tmp_path,
        comparable_conflicts=comparable_conflicts,
        control_price_differences=control_price_differences,
    )

    with pytest.raises(ValueError):
        load_primary_source_market_provenance(
            tmp_path,
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930", "000660"),
        )


def test_composed_gate_uses_fallback_and_restores_strict_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strict_failure = ValueError("raw status failed")

    def failing_loader(*_args: object, **_kwargs: object) -> MarketConsistencyProvenance:
        raise strict_failure

    fallback = cast(MarketConsistencyProvenance, object())
    monkeypatch.setattr(strict_gate, "load_market_consistency_provenance", failing_loader)
    monkeypatch.setattr(
        degraded_gate,
        "load_primary_source_market_provenance",
        lambda *_args, **_kwargs: fallback,
    )

    sentinel = cast(strict_gate.PipelineMarketConsistencyGate, object())

    def fake_gate(**_kwargs: Any) -> strict_gate.PipelineMarketConsistencyGate:
        loaded = strict_gate.load_market_consistency_provenance(
            Path("."),
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930", "000660"),
        )
        assert loaded is fallback
        return sentinel

    monkeypatch.setattr(strict_gate, "run_pipeline_market_consistency_gate", fake_gate)

    result = degraded_gate.run_pipeline_market_consistency_gate(
        output_root=Path("."),
        market_directory=Path("market"),
        decision_symbols=("005930", "000660"),
    )

    assert result is sentinel
    assert strict_gate.load_market_consistency_provenance is failing_loader


def test_composed_gate_preserves_original_failure_when_fallback_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strict_failure = ValueError("strict conflict")

    def failing_loader(*_args: object, **_kwargs: object) -> MarketConsistencyProvenance:
        raise strict_failure

    monkeypatch.setattr(strict_gate, "load_market_consistency_provenance", failing_loader)
    monkeypatch.setattr(
        degraded_gate,
        "load_primary_source_market_provenance",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("not scope mismatch")),
    )

    def fake_gate(**_kwargs: Any) -> strict_gate.PipelineMarketConsistencyGate:
        strict_gate.load_market_consistency_provenance(
            Path("."),
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930", "000660"),
        )
        raise AssertionError("unreachable")

    monkeypatch.setattr(strict_gate, "run_pipeline_market_consistency_gate", fake_gate)

    with pytest.raises(ValueError, match="strict conflict"):
        degraded_gate.run_pipeline_market_consistency_gate(
            output_root=Path("."),
            market_directory=Path("market"),
            decision_symbols=("005930", "000660"),
        )
    assert strict_gate.load_market_consistency_provenance is failing_loader
