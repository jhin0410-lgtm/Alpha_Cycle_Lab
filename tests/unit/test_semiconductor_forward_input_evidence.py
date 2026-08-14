from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    build_expectation_gap_decision_evidence,
)
from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY,
    build_semiconductor_forward_input_evidence,
    validate_forward_input_claim,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)

EVALUATION = date(2026, 8, 14)
REGISTRY = load_structural_source_registry(DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY)


def _claim(
    *,
    ticker: str = "000660",
    block_id: str = "dram_total",
    claim_type: str = "forward_driver",
    metric_id: str = "dram_bit_shipment_growth",
    kind: str = "qualitative",
    source_id: str = "sk_hynix_ir",
    source_url: str = "https://www.skhynix.com/example",
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
        "period_start": "2026-08-15" if claim_type == "forward_driver" else "2026-04-01",
        "period_end": "2026-12-31" if claim_type == "forward_driver" else "2026-06-30",
        "source_id": source_id,
        "source_url": source_url,
        "source_published_date": "2026-07-31",
        "semantics_certified": numeric,
        "source_vintage_certified": numeric,
        "reuse_or_license_basis_documented": False,
    }


def test_forward_input_metric_must_belong_to_issuer_block_contract() -> None:
    raw = _claim(metric_id="foundry_utilization")
    with pytest.raises(ValueError, match="outside issuer block contract"):
        validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)


def test_source_identity_and_domain_are_registry_bound() -> None:
    raw = _claim(source_url="https://example.com/not-sk-hynix")
    with pytest.raises(ValueError, match="outside registered domains"):
        validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)

    wrong_issuer = _claim(source_id="samsung_ir", source_url="https://www.samsung.com/example")
    with pytest.raises(ValueError, match="does not belong to ticker"):
        validate_forward_input_claim(wrong_issuer, REGISTRY, evaluation_date=EVALUATION)


def test_qualitative_evidence_never_becomes_numeric_driver_coverage() -> None:
    evidence = build_semiconductor_forward_input_evidence(
        [_claim()],
        REGISTRY,
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


def test_numeric_issuer_guidance_requires_certification_and_future_period_to_be_model_input() -> None:
    raw = _claim(kind="numeric")
    claim = validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)
    assert claim.numeric_model_input_eligible is True

    raw["source_vintage_certified"] = False
    uncertified = validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)
    assert uncertified.evidence_kind == "numeric"
    assert uncertified.numeric_model_input_eligible is False

    raw = _claim(kind="numeric")
    raw["period_end"] = "2026-06-30"
    historical = validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)
    assert historical.numeric_model_input_eligible is False


def test_peer_numeric_evidence_cannot_become_issuer_numeric_model_input() -> None:
    raw = _claim(
        kind="numeric",
        source_id="micron_ir",
        source_url="https://investors.micron.com/example",
    )
    claim = validate_forward_input_claim(raw, REGISTRY, evaluation_date=EVALUATION)
    assert claim.source_role == "peer_ir"
    assert claim.numeric_model_input_eligible is False


def test_qualitative_baseline_does_not_satisfy_numeric_baseline() -> None:
    evidence = build_semiconductor_forward_input_evidence(
        [
            _claim(
                claim_type="baseline",
                metric_id="dram_revenue_or_company_memory_bridge",
            )
        ],
        REGISTRY,
        evaluation_date=EVALUATION,
    )
    dram = evidence.block_coverage.loc[
        evidence.block_coverage["ticker"].eq("000660")
        & evidence.block_coverage["block_id"].eq("dram_total")
    ].iloc[0]
    assert int(dram["covered_baseline_count"]) == 1
    assert int(dram["numeric_baseline_count"]) == 0
    assert bool(dram["numeric_baseline_complete"]) is False


def test_expectation_gap_reads_explicit_forward_input_coverage_before_history() -> None:
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
