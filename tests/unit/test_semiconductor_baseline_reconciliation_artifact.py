from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_baseline_reconciliation_decision_evidence import (
    load_semiconductor_baseline_reconciliation_decision_evidence,
)
from alpha_cycle.semiconductor_baseline_reconciliation_cli import (
    capture_semiconductor_baseline_reconciliation,
)

EVALUATION = date(2026, 8, 14)


def _facts(document: Path) -> list[dict[str, object]]:
    common: dict[str, object] = {
        "ticker": "005930",
        "scope_id": "sdc",
        "unit": "KRW_trillion",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "source_id": "samsung_ir",
        "source_url": "https://www.samsung.com/global/ir/example",
        "source_published_date": "2026-07-30",
        "source_document_path": str(document),
        "semantics_certified": True,
    }
    return [
        {**common, "metric_id": "revenue", "value": 7.5},
        {**common, "metric_id": "operating_income", "value": 0.7},
    ]


def _capture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    document = tmp_path / "samsung-2q26.pdf"
    document.write_bytes(b"official-test-document-bytes")
    output = tmp_path / "baseline"
    result = capture_semiconductor_baseline_reconciliation(
        _facts(document),
        evaluation_date=EVALUATION,
        output=output,
    )
    return output / "latest_semiconductor_baseline_reconciliation.json", result


def test_baseline_artifact_archives_source_bytes_and_rebuilds(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    evidence = load_semiconductor_baseline_reconciliation_decision_evidence(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert evidence.evidence.evidence_id == result["evidence_id"]
    sdc = evidence.evidence.bridge_coverage.loc[
        evidence.evidence.bridge_coverage["ticker"].eq("005930")
        & evidence.evidence.bridge_coverage["block_id"].eq("sdc")
    ].iloc[0]
    assert bool(sdc["baseline_bridge_certified"]) is True
    assert evidence.residual_derivation_enabled is False
    assert evidence.internal_estimate_enabled is False


def test_tampered_archived_source_bytes_fail_closed(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    facts = pd.read_json(Path(str(result["facts_path"])))
    archived_path = Path(str(facts.iloc[0]["archived_document_path"]))
    archived_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="archived document hash mismatch"):
        load_semiconductor_baseline_reconciliation_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_tampered_bridge_coverage_fails_closed(tmp_path: Path) -> None:
    pointer, result = _capture(tmp_path)
    coverage_path = Path(str(result["bridge_coverage_path"]))
    frame = pd.read_csv(coverage_path)
    frame.loc[:, "baseline_bridge_certified"] = True
    frame.loc[:, "certified_output_count"] = frame["required_output_count"]
    frame.to_csv(coverage_path, index=False)
    with pytest.raises(ValueError, match="bridge coverage does not reproduce"):
        load_semiconductor_baseline_reconciliation_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_baseline_evaluation_date_mismatch_fails_closed(tmp_path: Path) -> None:
    pointer, _ = _capture(tmp_path)
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        load_semiconductor_baseline_reconciliation_decision_evidence(
            pointer,
            evaluation_date=date(2026, 8, 15),
        )
