from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_forward_input_decision_evidence import (
    load_semiconductor_forward_input_decision_evidence,
)
from alpha_cycle.semiconductor_forward_input_cli import capture_forward_input_evidence

EVALUATION = date(2026, 8, 14)


def _claims() -> list[dict[str, object]]:
    return [
        {
            "ticker": "000660",
            "block_id": "dram_total",
            "claim_type": "forward_driver",
            "metric_id": "dram_bit_shipment_growth",
            "evidence_kind": "qualitative",
            "statement": "issuer commentary supports directional demand context",
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


def _capture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    output = tmp_path / "forward-input"
    result = capture_forward_input_evidence(
        _claims(),
        evaluation_date=EVALUATION,
        output=output,
    )
    return output / "latest_semiconductor_forward_input_evidence.json", result


def test_forward_input_artifact_rebuilds_from_claims_and_archived_registry(
    tmp_path: Path,
) -> None:
    pointer, result = _capture(tmp_path)
    evidence = load_semiconductor_forward_input_decision_evidence(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert evidence.evidence_id == result["evidence_id"]
    assert set(evidence.issuer_coverage["ticker"].astype(str)) == {"000660", "005930"}
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_forward_input_tampered_coverage_fails_closed(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    coverage_path = Path(str(result["issuer_coverage_path"]))
    frame = pd.read_csv(coverage_path)
    frame.loc[frame["ticker"].astype(str).str.zfill(6).eq("000660"), "all_numeric_inputs_covered"] = True
    frame.to_csv(coverage_path, index=False)

    with pytest.raises(ValueError, match="issuer coverage does not reproduce"):
        load_semiconductor_forward_input_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_forward_input_tampered_archived_registry_fails_closed(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    registry_path = Path(str(result["source_registry_path"]))
    registry_path.write_text(registry_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="registry hash mismatch"):
        load_semiconductor_forward_input_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_forward_input_evaluation_date_mismatch_fails_closed(tmp_path: Path) -> None:
    pointer, _ = _capture(tmp_path)
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        load_semiconductor_forward_input_decision_evidence(
            pointer,
            evaluation_date=date(2026, 8, 15),
        )
