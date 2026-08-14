from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.semiconductor_baseline_allocation import (
    validate_source_bound_allocation_input,
)
from alpha_cycle.intelligence.semiconductor_baseline_allocation_artifact import (
    ALLOCATION_SOURCE_RESOLVERS,
    VerifiedAllocationSourceBundle,
    build_skhynix_revenue_allocation_evidence,
    capture_semiconductor_baseline_allocation,
    load_semiconductor_baseline_allocation_evidence,
)

EVALUATION_DATE = date(2026, 8, 14)
PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)
RESOLVER_ID = "test_skhynix_2026q2_official_numeric_v1"


def _id(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _input(
    semantic_id: str,
    value: float,
    unit: str,
    evidence_id: str,
):
    return validate_source_bound_allocation_input(
        {
            "ticker": "000660",
            "semantic_id": semantic_id,
            "value": value,
            "unit": unit,
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
            "source_evidence_id": evidence_id,
        },
        verified_evidence_ids={evidence_id},
    )


def _resolver(
    source_reference: str | Path,
    evaluation_date: date,
) -> VerifiedAllocationSourceBundle:
    source = Path(source_reference)
    source_reference_id = hashlib.sha256(source.read_bytes()).hexdigest()
    return VerifiedAllocationSourceBundle(
        resolver_id=RESOLVER_ID,
        ticker="000660",
        evaluation_date=evaluation_date,
        source_reference_id=source_reference_id,
        inputs=(
            _input(
                "reported_company_revenue",
                100.0,
                "KRW_trillion",
                _id("company_revenue"),
            ),
            _input("dram_revenue_share", 70.0, "percent", _id("dram_share")),
            _input("nand_revenue_share", 30.0, "percent", _id("nand_share")),
        ),
    )


def _changed_resolver(
    source_reference: str | Path,
    evaluation_date: date,
) -> VerifiedAllocationSourceBundle:
    bundle = _resolver(source_reference, evaluation_date)
    return VerifiedAllocationSourceBundle(
        resolver_id=bundle.resolver_id,
        ticker=bundle.ticker,
        evaluation_date=bundle.evaluation_date,
        source_reference_id=bundle.source_reference_id,
        inputs=(
            bundle.inputs[0],
            _input("dram_revenue_share", 69.0, "percent", _id("dram_share")),
            _input("nand_revenue_share", 31.0, "percent", _id("nand_share")),
        ),
    )


def test_production_allocation_resolver_registry_is_intentionally_empty(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"official-source-placeholder-for-contract-test")

    assert ALLOCATION_SOURCE_RESOLVERS == {}
    with pytest.raises(ValueError, match="source resolver is not registered"):
        build_skhynix_revenue_allocation_evidence(
            source,
            evaluation_date=EVALUATION_DATE,
            resolver_id=RESOLVER_ID,
        )


def test_source_resolver_can_certify_revenue_only_without_widening_gates(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source-bounded-inputs")

    evidence = build_skhynix_revenue_allocation_evidence(
        source,
        evaluation_date=EVALUATION_DATE,
        resolver_id=RESOLVER_ID,
        resolvers={RESOLVER_ID: _resolver},
    )

    reconciliation = evidence.reconciliation
    assert reconciliation.required_revenue_blocks == ("dram_total", "nand_and_solutions")
    assert reconciliation.allocated_revenue_blocks == ("dram_total", "nand_and_solutions")
    assert reconciliation.missing_revenue_blocks == ()
    assert reconciliation.allocated_revenue_total == pytest.approx(100.0)
    assert reconciliation.reconciliation_delta == pytest.approx(0.0)
    assert reconciliation.revenue_reconciliation_certified is True
    assert reconciliation.revenue_model_input_ready is True
    assert reconciliation.profitability_baseline_certified is False
    assert reconciliation.full_baseline_certified is False
    assert evidence.source_fact is False
    assert evidence.profitability_baseline_certified is False
    assert evidence.full_baseline_certified is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False
    assert all(allocation.source_fact is False for allocation in evidence.allocations)


def test_capture_and_loader_reconstruct_from_source_resolver(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"stable-source-bytes")
    output = tmp_path / "allocation"

    captured = capture_semiconductor_baseline_allocation(
        source,
        evaluation_date=EVALUATION_DATE,
        resolver_id=RESOLVER_ID,
        output=output,
        captured_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        resolvers={RESOLVER_ID: _resolver},
    )
    pointer = output / "latest_semiconductor_baseline_allocation.json"
    loaded = load_semiconductor_baseline_allocation_evidence(
        pointer,
        evaluation_date=EVALUATION_DATE,
        resolvers={RESOLVER_ID: _resolver},
    )

    assert captured["evidence_id"] == loaded.evidence_id
    assert loaded.reconciliation.revenue_reconciliation_certified is True
    assert loaded.reconciliation.revenue_model_input_ready is True
    assert loaded.reconciliation.full_baseline_certified is False

    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_payload["source_fact"] is False
    assert pointer_payload["profitability_baseline_certified"] is False
    assert pointer_payload["full_baseline_certified"] is False
    assert pointer_payload["numeric_forecast_enabled"] is False
    assert pointer_payload["decision_score_enabled"] is False


def test_loader_rejects_tampered_persisted_revenue_readiness(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"stable-source-bytes")
    output = tmp_path / "allocation"
    captured = capture_semiconductor_baseline_allocation(
        source,
        evaluation_date=EVALUATION_DATE,
        resolver_id=RESOLVER_ID,
        output=output,
        captured_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        resolvers={RESOLVER_ID: _resolver},
    )
    payload_path = Path(str(captured["baseline_allocation_path"]))
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["revenue_model_input_ready"] = False
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="persisted field mismatch"):
        load_semiconductor_baseline_allocation_evidence(
            output / "latest_semiconductor_baseline_allocation.json",
            evaluation_date=EVALUATION_DATE,
            resolvers={RESOLVER_ID: _resolver},
        )


def test_loader_rejects_source_semantic_drift_after_capture(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"stable-source-bytes")
    output = tmp_path / "allocation"
    capture_semiconductor_baseline_allocation(
        source,
        evaluation_date=EVALUATION_DATE,
        resolver_id=RESOLVER_ID,
        output=output,
        captured_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        resolvers={RESOLVER_ID: _resolver},
    )

    with pytest.raises(ValueError, match="does not reproduce"):
        load_semiconductor_baseline_allocation_evidence(
            output / "latest_semiconductor_baseline_allocation.json",
            evaluation_date=EVALUATION_DATE,
            resolvers={RESOLVER_ID: _changed_resolver},
        )
