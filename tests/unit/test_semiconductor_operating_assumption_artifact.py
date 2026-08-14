from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_operating_assumption_decision_evidence import (
    load_semiconductor_operating_assumption_decision_evidence,
)
from alpha_cycle.semiconductor_forward_input_cli import capture_forward_input_evidence
from alpha_cycle.semiconductor_operating_assumption_cli import (
    capture_operating_assumption_pack,
)

EVALUATION = date(2026, 8, 14)


def _forward_claims() -> list[dict[str, object]]:
    return [
        {
            "ticker": "000660",
            "block_id": "dram_total",
            "claim_type": "forward_driver",
            "metric_id": "dram_bit_shipment_growth",
            "evidence_kind": "qualitative",
            "statement": "issuer demand evidence",
            "numeric_value": None,
            "unit": None,
            "period_start": "2026-08-15",
            "period_end": "2026-12-31",
            "source_id": "sk_hynix_ir",
            "source_url": "https://www.skhynix.com/example",
            "source_published_date": "2026-07-31",
            "semantics_certified": False,
            "source_vintage_certified": False,
            "reuse_or_license_basis_documented": False,
        }
    ]


def _forward_pointer(tmp_path: Path) -> tuple[Path, str]:
    output = tmp_path / "forward"
    result = capture_forward_input_evidence(
        _forward_claims(),
        evaluation_date=EVALUATION,
        output=output,
    )
    claims = json.loads(Path(str(result["claims_path"])).read_text(encoding="utf-8"))
    return output / "latest_semiconductor_forward_input_evidence.json", str(claims[0]["claim_id"])


def _assumption(claim_id: str) -> dict[str, object]:
    return {
        "ticker": "000660",
        "block_id": "dram_total",
        "driver_id": "dram_bit_shipment_growth",
        "scenario": "base",
        "quarter_index": 1,
        "value": 0.1,
        "unit": "fraction_qoq",
        "method_id": "memory_driver_scenario_v1",
        "method_version": "1.0",
        "method_status": "observationally_calibrated",
        "method_version_frozen": True,
        "supporting_evidence_ids": [claim_id],
        "rationale": "Explicit internal scenario input supported by bounded issuer evidence.",
        "invalidation_condition": "Demand evidence reverses materially.",
    }


def _capture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    forward_pointer, claim_id = _forward_pointer(tmp_path)
    output = tmp_path / "assumptions"
    result = capture_operating_assumption_pack(
        [_assumption(claim_id)],
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        forward_input_pointer=forward_pointer,
        output=output,
    )
    return output / "latest_semiconductor_operating_assumptions.json", result


def test_operating_assumption_artifact_rebuilds_with_verified_forward_evidence(
    tmp_path: Path,
) -> None:
    pointer, result = _capture(tmp_path)
    evidence = load_semiconductor_operating_assumption_decision_evidence(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert evidence.pack.pack_id == result["pack_id"]
    assert evidence.pack.assumptions[0].supporting_evidence_verified is True
    assert evidence.pack.assumptions[0].model_use_ready is True
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_operating_assumption_tampered_coverage_fails_closed(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    coverage_path = Path(str(result["scenario_coverage_path"]))
    frame = pd.read_csv(coverage_path)
    frame.loc[:, "assumption_coverage_complete"] = True
    frame.to_csv(coverage_path, index=False)
    with pytest.raises(ValueError, match="coverage does not reproduce"):
        load_semiconductor_operating_assumption_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_operating_assumption_evaluation_date_mismatch_fails_closed(tmp_path: Path) -> None:
    pointer, _ = _capture(tmp_path)
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        load_semiconductor_operating_assumption_decision_evidence(
            pointer,
            evaluation_date=date(2026, 8, 15),
        )


def test_operating_assumption_support_must_exist_in_linked_forward_artifact(
    tmp_path: Path,
) -> None:
    forward_pointer, _ = _forward_pointer(tmp_path)
    output = tmp_path / "bad-assumptions"
    result = capture_operating_assumption_pack(
        [_assumption("f" * 64)],
        evaluation_date=EVALUATION,
        horizon_quarters=4,
        forward_input_pointer=forward_pointer,
        output=output,
    )
    assumptions = json.loads(Path(str(result["assumptions_path"])).read_text(encoding="utf-8"))
    assert assumptions[0]["supporting_evidence_verified"] is False
    assert assumptions[0]["model_use_ready"] is False
