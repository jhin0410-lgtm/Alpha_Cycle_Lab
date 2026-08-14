from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence.semiconductor_baseline_reconciliation import (
    DEFAULT_BASELINE_SOURCE_REGISTRY,
    build_semiconductor_baseline_reconciliation,
    validate_baseline_fact,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)

EVALUATION = date(2026, 8, 14)
REGISTRY = load_structural_source_registry(DEFAULT_BASELINE_SOURCE_REGISTRY)
DOC_HASH = "a" * 64


def _fact(
    metric_id: str,
    *,
    scope_id: str = "sdc",
    value: float = 1.0,
    period_start: str = "2026-04-01",
    period_end: str = "2026-06-30",
    semantics_certified: bool = True,
) -> dict[str, object]:
    return {
        "ticker": "005930",
        "scope_id": scope_id,
        "metric_id": metric_id,
        "value": value,
        "unit": "KRW_trillion",
        "period_start": period_start,
        "period_end": period_end,
        "source_id": "samsung_ir",
        "source_url": "https://www.samsung.com/global/ir/example",
        "source_published_date": "2026-07-30",
        "source_document_sha256": DOC_HASH,
        "source_bytes_archived": True,
        "semantics_certified": semantics_certified,
        "source_vintage_certified": True,
    }


def test_same_scope_same_period_direct_outputs_can_certify_bridge() -> None:
    evidence = build_semiconductor_baseline_reconciliation(
        [_fact("revenue", value=7.5), _fact("operating_income", value=0.7)],
        REGISTRY,
        evaluation_date=EVALUATION,
    )
    sdc = evidence.bridge_coverage.loc[
        evidence.bridge_coverage["ticker"].eq("005930")
        & evidence.bridge_coverage["block_id"].eq("sdc")
    ].iloc[0]
    assert sdc["baseline_bridge_status"] == "certified_direct_fact_bridge"
    assert bool(sdc["baseline_bridge_certified"]) is True
    assert int(sdc["certified_output_count"]) == 2
    assert evidence.residual_derivation_enabled is False
    assert evidence.internal_estimate_enabled is False


def test_memory_revenue_alone_cannot_stand_in_for_memory_profit_bridge() -> None:
    evidence = build_semiconductor_baseline_reconciliation(
        [_fact("revenue", scope_id="ds_memory", value=120.8)],
        REGISTRY,
        evaluation_date=EVALUATION,
    )
    memory = evidence.bridge_coverage.loc[
        evidence.bridge_coverage["ticker"].eq("005930")
        & evidence.bridge_coverage["block_id"].eq("ds_memory")
    ].iloc[0]
    assert memory["baseline_bridge_status"] == "missing_required_direct_facts"
    assert bool(memory["baseline_bridge_certified"]) is False
    assert int(memory["certified_output_count"]) == 0


def test_mismatched_periods_do_not_form_a_bridge() -> None:
    evidence = build_semiconductor_baseline_reconciliation(
        [
            _fact("revenue", value=7.5),
            _fact(
                "operating_income",
                value=0.7,
                period_start="2026-01-01",
                period_end="2026-03-31",
            ),
        ],
        REGISTRY,
        evaluation_date=EVALUATION,
    )
    sdc = evidence.bridge_coverage.loc[
        evidence.bridge_coverage["ticker"].eq("005930")
        & evidence.bridge_coverage["block_id"].eq("sdc")
    ].iloc[0]
    assert bool(sdc["baseline_bridge_certified"]) is False


def test_uncertified_semantics_remain_non_bridge_eligible() -> None:
    fact = validate_baseline_fact(
        _fact("revenue", semantics_certified=False),
        REGISTRY,
        evaluation_date=EVALUATION,
    )
    assert fact.bridge_eligible is False


def test_wrong_issuer_source_or_scope_metric_fails_closed() -> None:
    wrong_source = _fact("revenue")
    wrong_source["source_id"] = "sk_hynix_ir"
    wrong_source["source_url"] = "https://www.skhynix.com/example"
    with pytest.raises(ValueError, match="matching issuer IR"):
        validate_baseline_fact(wrong_source, REGISTRY, evaluation_date=EVALUATION)

    with pytest.raises(ValueError, match="outside block output contract"):
        validate_baseline_fact(
            _fact("operating_expense", scope_id="sdc"),
            REGISTRY,
            evaluation_date=EVALUATION,
        )
