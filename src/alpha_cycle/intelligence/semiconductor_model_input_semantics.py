"""Semantic classes for semiconductor forward-model baseline requirements.

A source fact is not automatically a model baseline. Several issuer contracts use
"bridge" requirements because public IR discloses only part of the economics needed
for a block. Those requirements must be satisfied by a separately reconciled artifact,
not by attaching one convenient scalar to the bridge name.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
)


@dataclass(frozen=True)
class BaselineRequirementSemantics:
    ticker: str
    block_id: str
    metric_id: str
    requirement_kind: str
    direct_numeric_source_fact_sufficient: bool
    reconciliation_required: bool

    def __post_init__(self) -> None:
        allowed = {"direct_numeric_or_share", "reconciliation_artifact"}
        if self.requirement_kind not in allowed:
            raise ValueError("Baseline requirement kind is invalid")
        if self.direct_numeric_source_fact_sufficient == self.reconciliation_required:
            raise ValueError("Baseline requirement semantics must choose exactly one path")


_BASELINE_KINDS: dict[tuple[str, str, str], str] = {
    (
        "000660",
        "dram_total",
        "dram_revenue_or_company_memory_bridge",
    ): "reconciliation_artifact",
    (
        "000660",
        "hbm_mix_overlay",
        "hbm_mix_or_revenue_share",
    ): "direct_numeric_or_share",
    (
        "000660",
        "nand_and_solutions",
        "nand_solution_revenue_bridge",
    ): "reconciliation_artifact",
    (
        "000660",
        "other_products_services",
        "other_products_services_revenue_bridge",
    ): "reconciliation_artifact",
    (
        "000660",
        "corporate_other",
        "company_to_memory_reconciliation",
    ): "reconciliation_artifact",
    (
        "005930",
        "ds_memory",
        "ds_memory_revenue_and_profit_bridge",
    ): "reconciliation_artifact",
    (
        "005930",
        "ds_foundry_system_lsi",
        "foundry_system_lsi_revenue_profit_bridge",
    ): "reconciliation_artifact",
    (
        "005930",
        "dx",
        "dx_revenue_profit_bridge",
    ): "reconciliation_artifact",
    (
        "005930",
        "sdc",
        "sdc_revenue_profit_bridge",
    ): "reconciliation_artifact",
    (
        "005930",
        "harman",
        "harman_revenue_profit_bridge",
    ): "reconciliation_artifact",
    (
        "005930",
        "corporate_eliminations",
        "segment_to_consolidated_reconciliation",
    ): "reconciliation_artifact",
}


def baseline_requirement_semantics(
    ticker: str,
    block_id: str,
    metric_id: str,
) -> BaselineRequirementSemantics:
    ticker_key = str(ticker).zfill(6)
    if ticker_key not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
        raise ValueError(f"Forward model contract not registered: {ticker_key}")
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker_key]
    block = next((item for item in contract.blocks if item.block_id == block_id), None)
    if block is None or metric_id not in block.required_baseline_metrics:
        raise ValueError(
            f"Baseline requirement is outside issuer contract: {ticker_key}/{block_id}/{metric_id}"
        )
    key = (ticker_key, block_id, metric_id)
    kind = _BASELINE_KINDS.get(key)
    if kind is None:
        raise ValueError(f"Baseline requirement semantics are not registered: {key}")
    return BaselineRequirementSemantics(
        ticker=ticker_key,
        block_id=block_id,
        metric_id=metric_id,
        requirement_kind=kind,
        direct_numeric_source_fact_sufficient=kind == "direct_numeric_or_share",
        reconciliation_required=kind == "reconciliation_artifact",
    )


def audit_baseline_semantics_registry() -> tuple[str, ...]:
    expected = {
        (ticker, block.block_id, metric)
        for ticker, contract in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.items()
        for block in contract.blocks
        for metric in block.required_baseline_metrics
    }
    registered = set(_BASELINE_KINDS)
    missing = sorted(expected - registered)
    extra = sorted(registered - expected)
    warnings: list[str] = []
    warnings.extend("missing:" + "/".join(item) for item in missing)
    warnings.extend("extra:" + "/".join(item) for item in extra)
    return tuple(warnings)


__all__ = [
    "BaselineRequirementSemantics",
    "audit_baseline_semantics_registry",
    "baseline_requirement_semantics",
]
