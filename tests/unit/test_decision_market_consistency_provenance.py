"""Tests for fail-closed decision market-consistency provenance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.decision_provenance import (
    build_decision_evidence_envelope,
    write_decision_evidence_envelope,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    load_market_consistency_provenance,
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


def _consistency_case(
    root: Path,
    *,
    status: str = "passed",
    classification: str = "equivalent_scope_observed",
    market_id: str = MARKET_ID,
    assessment_status: str = "completed",
) -> tuple[Path, Path]:
    result_path = root / "market-source-consistency" / "case" / "consistency.json"
    assessment_path = result_path.parent / "market_scope_assessment.json"
    live_passed = status == "passed"
    raw_payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "checked_at_utc": "2026-08-05T04:00:00+00:00",
        "checked_at_kst": "2026-08-05T13:00:00+09:00",
        "expected_symbols": list(SYMBOLS),
        "toss_snapshot_id": market_id,
        "toss_captured_at": "2026-08-05T04:00:00+00:00",
        "toss_snapshot_age_seconds": 0.0,
        "toss_directory": "market",
        "toss_resolution_source": "explicit_pipeline_market_directory",
        "kiwoom_snapshot_id": KIWOOM_ID,
        "kiwoom_captured_at": "2026-08-05T04:00:00+00:00",
        "kiwoom_snapshot_age_seconds": 0.0,
        "kiwoom_directory": "kiwoom",
        "historical_cutoff_date_exclusive": "2026-08-05",
        "historical_days_required_per_symbol": 20,
        "historical_rows_compared": 60,
        "historical_symbols_passed": list(SYMBOLS),
        "historical_price_conflict_count": 0,
        "historical_volume_mismatch_count": 0,
        "live_quote_status": "passed" if live_passed else "not_comparable",
        "live_quote_comparable_count": 3 if live_passed else 0,
        "live_quote_conflict_count": 0,
        "live_capture_gap_seconds": 0.0,
        "decision_integration_eligible": live_passed,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "warnings": [],
        "failures": [],
        "daily_comparisons_file": "daily_price_comparisons.csv",
        "quote_comparisons_file": "live_quote_comparisons.csv",
    }
    result_id = _result_id(raw_payload)
    raw_payload["result_id"] = result_id
    _write(result_path, raw_payload)

    assessment_payload: dict[str, object] = {
        "schema_version": "1.3",
        "status": status,
        "classification": classification,
        "checked_at_utc": raw_payload["checked_at_utc"],
        "checked_at_kst": raw_payload["checked_at_kst"],
        "raw_result_id": result_id,
        "raw_result_path": str(result_path.resolve()),
        "raw_status": status,
        "raw_price_difference_count": 0,
        "tolerance_conflict_count": 0,
        "comparable_scope_price_conflict_count": 0,
        "scope_incompatible_row_count": 0,
        "historical_scope_status": "comparable",
        "toss_historical_market_scope": "unadjusted_unspecified_venue",
        "kiwoom_historical_market_scope": "kiwoom_opt10081_unadjusted",
        "scope_incompatible_symbols": [],
        "control_symbols_verified": ["005935"],
        "live_quote_status": raw_payload["live_quote_status"],
        "live_quote_conflict_count": 0,
        "raw_failures": [],
        "decision_integration_eligible": live_passed,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "rationale": ["Completed-session historical OHLC values match exactly."],
        "symbols": [{"ticker": ticker} for ticker in SYMBOLS],
    }
    assessment_id = _assessment_id(assessment_payload)
    assessment_payload["assessment_id"] = assessment_id
    _write(assessment_path, assessment_payload)

    raw_pointer = {
        "status": status,
        "result_id": result_id,
        "checked_at_utc": raw_payload["checked_at_utc"],
        "result_path": str(result_path.resolve()),
        "raw_decision_integration_eligible": live_passed,
        "decision_integration_eligible": live_passed,
        "assessment_status": assessment_status,
        "assessment_id": assessment_id,
        "assessment_path": str(assessment_path.resolve()),
        "classification": classification,
        "assessment_failure": None,
        "historical_price_conflict_count": 0,
        "live_quote_status": raw_payload["live_quote_status"],
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    assessment_pointer = {
        "status": status,
        "classification": classification,
        "assessment_id": assessment_id,
        "assessment_path": str(assessment_path.resolve()),
        "raw_result_id": result_id,
        "raw_result_path": str(result_path.resolve()),
        "decision_integration_eligible": live_passed,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    _write(root / "latest_market_consistency.json", raw_pointer)
    _write(root / "latest_market_scope_assessment.json", assessment_pointer)
    return result_path, assessment_path


def _decision_directory(root: Path) -> Path:
    directory = root / "decision"
    _write(
        directory / "manifest.json",
        {
            "snapshot_id": DECISION_ID,
            "market_snapshot_id": MARKET_ID,
        },
    )
    return directory


def test_live_passed_provenance_certifies_reference_price(tmp_path: Path) -> None:
    _consistency_case(tmp_path)
    provenance = load_market_consistency_provenance(
        tmp_path,
        market_snapshot_id=MARKET_ID,
        decision_symbols=("005930", "000660"),
    )

    assert provenance.mode == "live_certified"
    assert provenance.historical_verified is True
    assert provenance.live_price_certified is True
    assert provenance.decision_integration_eligible is True
    envelope = build_decision_evidence_envelope(
        _decision_directory(tmp_path),
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=provenance,
        now=datetime(2026, 8, 5, 5, tzinfo=UTC),
    )
    written = write_decision_evidence_envelope(tmp_path / "envelopes", envelope)
    manifest = json.loads(written[0].read_text(encoding="utf-8"))
    assert manifest["envelope_id"] == envelope.envelope_id
    assert manifest["market_provenance_status"] == "live_certified"
    assert manifest["reference_price_cross_provider_certified"] is True
    assert manifest["order_api_enabled"] is False


def test_historical_only_provenance_does_not_certify_reference_price(
    tmp_path: Path,
) -> None:
    _consistency_case(tmp_path, status="passed_historical_only")
    provenance = load_market_consistency_provenance(
        tmp_path,
        market_snapshot_id=MARKET_ID,
        decision_symbols=("005930", "000660"),
    )

    assert provenance.mode == "historical_only"
    assert provenance.historical_verified is True
    assert provenance.live_price_certified is False
    assert provenance.decision_integration_eligible is False


def test_missing_consistency_is_explicit_in_envelope(tmp_path: Path) -> None:
    envelope = build_decision_evidence_envelope(
        _decision_directory(tmp_path),
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=None,
        now=datetime(2026, 8, 5, 5, tzinfo=UTC),
    )

    assert envelope.market_provenance_status == "not_connected"
    assert envelope.reference_price_cross_provider_certified is False
    assert "market_consistency_not_connected" in envelope.warnings


def test_tampered_raw_result_id_is_rejected(tmp_path: Path) -> None:
    result_path, _ = _consistency_case(tmp_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["historical_rows_compared"] = 59
    _write(result_path, payload)

    with pytest.raises(ValueError, match="result_id does not match"):
        load_market_consistency_provenance(
            tmp_path,
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930",),
        )


def test_different_market_snapshot_is_rejected(tmp_path: Path) -> None:
    _consistency_case(tmp_path, market_id="e" * 64)

    with pytest.raises(ValueError, match="different market snapshot"):
        load_market_consistency_provenance(
            tmp_path,
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930",),
        )


def test_blocked_market_scope_classification_is_rejected(tmp_path: Path) -> None:
    _consistency_case(
        tmp_path,
        classification="inferred_venue_scope_mismatch",
    )

    with pytest.raises(ValueError, match="classification blocks decisions"):
        load_market_consistency_provenance(
            tmp_path,
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930",),
        )


def test_pending_assessment_pointer_is_rejected(tmp_path: Path) -> None:
    _consistency_case(tmp_path, assessment_status="pending")

    with pytest.raises(ValueError, match="assessment is not complete"):
        load_market_consistency_provenance(
            tmp_path,
            market_snapshot_id=MARKET_ID,
            decision_symbols=("005930",),
        )
