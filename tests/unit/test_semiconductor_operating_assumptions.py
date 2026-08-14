from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence.semiconductor_operating_assumptions import (
    build_operating_assumption_pack,
    validate_operating_assumption,
)

EVALUATION = date(2026, 8, 14)
SUPPORT = "a" * 64


def _assumption(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "ticker": "000660",
        "block_id": "dram_total",
        "driver_id": "dram_bit_shipment_growth",
        "scenario": "base",
        "quarter_index": 1,
        "value": 0.10,
        "unit": "fraction_qoq",
        "method_id": "memory_driver_scenario_v1",
        "method_version": "1.0",
        "method_status": "observationally_calibrated",
        "method_version_frozen": True,
        "supporting_evidence_ids": [SUPPORT],
        "rationale": "Translate bounded memory demand evidence into an explicit scenario input.",
        "invalidation_condition": "Demand or price evidence reverses materially.",
    }
    raw.update(overrides)
    return raw


def test_assumption_is_internal_model_choice_not_source_fact() -> None:
    item = validate_operating_assumption(
        _assumption(),
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        verified_evidence_ids={SUPPORT},
    )
    assert item.source_fact is False
    assert item.scenario_probability_enabled is False
    assert item.decision_score_enabled is False
    assert item.model_use_ready is True


def test_unverified_or_unfrozen_method_stays_out_of_model_use() -> None:
    unverified = validate_operating_assumption(
        _assumption(),
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        verified_evidence_ids=set(),
    )
    assert unverified.model_use_ready is False

    unfrozen = validate_operating_assumption(
        _assumption(method_version_frozen=False),
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        verified_evidence_ids={SUPPORT},
    )
    assert unfrozen.model_use_ready is False


def test_driver_and_quarter_must_match_issuer_contract() -> None:
    with pytest.raises(ValueError, match="outside issuer block contract"):
        validate_operating_assumption(
            _assumption(driver_id="foundry_utilization"),
            evaluation_date=EVALUATION,
            horizon_quarters=4,
            verified_evidence_ids={SUPPORT},
        )
    with pytest.raises(ValueError, match="outside model horizon"):
        validate_operating_assumption(
            _assumption(quarter_index=5),
            evaluation_date=EVALUATION,
            horizon_quarters=4,
            verified_evidence_ids={SUPPORT},
        )


def test_pack_rejects_duplicate_driver_quarter_scenario() -> None:
    with pytest.raises(ValueError, match="duplicate driver-quarter"):
        build_operating_assumption_pack(
            [_assumption(), _assumption(value=0.2)],
            evaluation_date=EVALUATION,
            horizon_quarters=4,
            verified_evidence_ids={SUPPORT},
        )


def test_partial_assumption_pack_reports_missing_driver_quarters_without_forecast() -> None:
    pack = build_operating_assumption_pack(
        [_assumption()],
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        verified_evidence_ids={SUPPORT},
    )
    hynix_base = pack.scenario_coverage.loc[
        pack.scenario_coverage["ticker"].eq("000660")
        & pack.scenario_coverage["scenario"].eq("base")
    ].iloc[0]
    assert int(hynix_base["supplied_driver_quarter_count"]) == 1
    assert bool(hynix_base["assumption_coverage_complete"]) is False
    assert bool(hynix_base["model_use_assumptions_complete"]) is False
    assert pack.scenario_probabilities_enabled is False
    assert pack.numeric_forecast_enabled is False
    assert pack.decision_score_enabled is False
