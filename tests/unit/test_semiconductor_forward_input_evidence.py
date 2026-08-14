from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    build_expectation_gap_decision_evidence,
)
from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    build_semiconductor_forward_input_evidence,
    validate_forward_input_claim,
)

EVALUATION = date(2026, 8, 14)


def _claim(
    *,
    ticker: str = "000660",
    block_id: str = "dram_total",
    claim_type: str = "forward_driver",
    metric_id: str = "dram_bit_shipment_growth",
    kind: str = "qualitative",
) -> dict[str, object]:
    numeric = kind == "numeric"
    return {
        "ticker": ticker,
        "block_id": block_id,
        "claim_type": claim_type,
        "metric_id": metric_id,
        "evidence_kind": kind,
        "statement": "source-bounded test evidence",
        "numeric_value": 0.1 if numeric else None,
        "unit": "fraction" if numeric else None,
        "source_role": "issuer_ir",
        "source_url": "https://www.skhynix.com/example",
        "source_published_date": "2026-07-31",
        "semantics_certified": numeric,
        "source_vintage_certified": numeric,
        "reuse_or_license_basis_documented": False,
        "primary_source": True,
    }


def test_forward_input_metric_must_belong_to_issuer_block_contract() -> None:
    raw = _claim(metric_id="foundry_utilization")
    with pytest.raises(ValueError, match="outside issuer block contract"):
        validate_forward_input_claim(raw, evaluation_date=EVALUATION)


def test_qualitative_evidence_never_becomes_numeric_driver_coverage() -> None:
    evidence = build_semiconductor_forward_input_evidence(
        [_claim()],
        evaluation_date=EVALUATION,
    )
    dram = evidence.block_coverage.loc[
        evidence.block_coverage["ticker"].eq("000660")
        & evidence.block_coverage["block_id"].eq("dram_total")
    ].iloc[0]
    assert int(dram["covered_forward_driver_count"]) == 1
    assert int(dram["numeric_forward_driver_count"]) == 0
    assert bool(dram["numeric_model_input_ready"]) is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_numeric_driver_requires_semantics_vintage_and_unit() -> None:
    raw = _claim(kind="numeric")
    raw["source_vintage_certified"] = False
    with pytest.raises(ValueError, match="semantics and source vintage"):
        validate_forward_input_claim(raw, evaluation_date=EVALUATION)


def test_expectation_gap_reads_explicit_forward_input_coverage_before_history() -> None:
    import pandas as pd

    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "kis_forward_evidence_available": True,
                "kis_estimate_snapshot_change_available": False,
                "semiconductor_forward_required_block_count": 4,
                "semiconductor_forward_all_descriptive_inputs_covered": True,
                "semiconductor_forward_all_numeric_inputs_covered": False,
                "semiconductor_forward_internal_forward_model_certified": False,
                "semiconductor_transmission_history_ready": True,
            }
        ]
    )
    evidence = build_expectation_gap_decision_evidence(scorecards)
    row = evidence.rows.iloc[0]
    assert row["internal_forward_view_status"] == "descriptive_forward_inputs_only"
    assert bool(row["expectation_gap_enabled"]) is False
    assert bool(row["decision_score_enabled"]) is False
