"""Issuer-specific semiconductor forward operating model contract.

The semiconductor industry signal cannot be applied identically to SK hynix and
Samsung Electronics. SK hynix is predominantly memory-exposed, while Samsung's
listed-company earnings also depend on foundry/system LSI, DX, display, Harman,
and corporate/elimination effects. This module defines the evidence required
before Alpha Cycle may call an internal 4-8 quarter operating view 'certified'.
It does not fabricate missing segment forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForwardModelBlock:
    block_id: str
    additive_to_company_financials: bool
    required_baseline_metrics: tuple[str, ...]
    required_forward_drivers: tuple[str, ...]
    required_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.block_id.strip():
            raise ValueError("Forward model block_id cannot be blank")
        if not self.required_forward_drivers:
            raise ValueError("Forward model block requires forward drivers")
        if self.additive_to_company_financials and not self.required_outputs:
            raise ValueError("Additive model block requires financial outputs")


@dataclass(frozen=True)
class IssuerForwardModelContract:
    ticker: str
    issuer_name: str
    model_horizon_quarters: tuple[int, int]
    blocks: tuple[ForwardModelBlock, ...]
    company_outputs: tuple[str, ...]
    reconciliation_requirements: tuple[str, ...]
    invalidation_requirements: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Forward model ticker must be six digits")
        if not self.issuer_name.strip() or not self.blocks:
            raise ValueError("Forward model issuer/blocks cannot be empty")
        lower, upper = self.model_horizon_quarters
        if lower < 1 or upper < lower:
            raise ValueError("Forward model horizon is invalid")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise ValueError(f"Forward model repeats block_id: {self.ticker}")
        if not self.company_outputs or not self.reconciliation_requirements:
            raise ValueError("Forward model requires company outputs and reconciliation")


SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS: dict[str, IssuerForwardModelContract] = {
    "000660": IssuerForwardModelContract(
        ticker="000660",
        issuer_name="SK hynix",
        model_horizon_quarters=(4, 8),
        blocks=(
            ForwardModelBlock(
                block_id="dram_total",
                additive_to_company_financials=True,
                required_baseline_metrics=("dram_revenue_or_company_memory_bridge",),
                required_forward_drivers=(
                    "dram_bit_shipment_growth",
                    "dram_asp_change",
                    "dram_product_mix",
                    "fx",
                ),
                required_outputs=("revenue", "gross_profit_or_margin"),
            ),
            ForwardModelBlock(
                block_id="hbm_mix_overlay",
                additive_to_company_financials=False,
                required_baseline_metrics=("hbm_mix_or_revenue_share",),
                required_forward_drivers=(
                    "hbm_volume_growth",
                    "hbm_generation_mix",
                    "hbm_pricing_or_premium",
                    "hbm_capacity",
                    "hbm_yield",
                    "advanced_packaging_capacity",
                    "customer_qualification",
                ),
                required_outputs=("dram_mix_effect", "margin_mix_effect"),
            ),
            ForwardModelBlock(
                block_id="nand_and_solutions",
                additive_to_company_financials=True,
                required_baseline_metrics=("nand_solution_revenue_bridge",),
                required_forward_drivers=(
                    "nand_bit_shipment_growth",
                    "nand_asp_change",
                    "enterprise_ssd_mix",
                    "inventory",
                    "fx",
                ),
                required_outputs=("revenue", "gross_profit_or_margin"),
            ),
            ForwardModelBlock(
                block_id="corporate_other",
                additive_to_company_financials=True,
                required_baseline_metrics=("company_to_memory_reconciliation",),
                required_forward_drivers=("opex", "other_income_expense", "tax"),
                required_outputs=("operating_expense", "net_income_bridge"),
            ),
        ),
        company_outputs=(
            "revenue",
            "operating_income",
            "operating_margin",
            "net_income",
            "capex",
            "free_cash_flow",
            "ending_equity",
        ),
        reconciliation_requirements=(
            "product_blocks_reconcile_to_reported_company_baseline",
            "hbm_overlay_is_not_double_counted_as_additive_revenue",
            "quarterly_model_reconciles_to_annual_view",
            "cash_flow_and_equity_roll_forward_reconcile",
        ),
        invalidation_requirements=(
            "memory_price_reversal",
            "hbm_qualification_failure",
            "hbm_yield_or_packaging_bottleneck",
            "inventory_reaccumulation",
            "ai_memory_demand_break",
        ),
    ),
    "005930": IssuerForwardModelContract(
        ticker="005930",
        issuer_name="Samsung Electronics",
        model_horizon_quarters=(4, 8),
        blocks=(
            ForwardModelBlock(
                block_id="ds_memory",
                additive_to_company_financials=True,
                required_baseline_metrics=("ds_memory_revenue_and_profit_bridge",),
                required_forward_drivers=(
                    "dram_bit_shipment_growth",
                    "dram_asp_change",
                    "nand_bit_shipment_growth",
                    "nand_asp_change",
                    "hbm_volume_and_mix",
                    "hbm_capacity_yield_packaging",
                    "inventory_and_utilization",
                    "fx",
                ),
                required_outputs=("revenue", "operating_income"),
            ),
            ForwardModelBlock(
                block_id="ds_foundry_system_lsi",
                additive_to_company_financials=True,
                required_baseline_metrics=("foundry_system_lsi_revenue_profit_bridge",),
                required_forward_drivers=(
                    "foundry_utilization",
                    "wafer_pricing_and_mix",
                    "advanced_node_yield",
                    "customer_ramp",
                    "system_lsi_demand",
                ),
                required_outputs=("revenue", "operating_income"),
            ),
            ForwardModelBlock(
                block_id="dx",
                additive_to_company_financials=True,
                required_baseline_metrics=("dx_revenue_profit_bridge",),
                required_forward_drivers=(
                    "smartphone_units",
                    "smartphone_mix",
                    "component_cost",
                    "tv_appliance_demand",
                    "fx",
                ),
                required_outputs=("revenue", "operating_income"),
            ),
            ForwardModelBlock(
                block_id="sdc",
                additive_to_company_financials=True,
                required_baseline_metrics=("sdc_revenue_profit_bridge",),
                required_forward_drivers=(
                    "oled_panel_volume",
                    "panel_mix_and_pricing",
                    "customer_product_cycle",
                ),
                required_outputs=("revenue", "operating_income"),
            ),
            ForwardModelBlock(
                block_id="harman",
                additive_to_company_financials=True,
                required_baseline_metrics=("harman_revenue_profit_bridge",),
                required_forward_drivers=("auto_end_demand", "order_backlog", "margin"),
                required_outputs=("revenue", "operating_income"),
            ),
            ForwardModelBlock(
                block_id="corporate_eliminations",
                additive_to_company_financials=True,
                required_baseline_metrics=("segment_to_consolidated_reconciliation",),
                required_forward_drivers=(
                    "intersegment_eliminations",
                    "corporate_cost",
                    "other_income_expense",
                    "tax",
                ),
                required_outputs=("consolidation_bridge", "net_income_bridge"),
            ),
        ),
        company_outputs=(
            "revenue",
            "operating_income",
            "operating_margin",
            "net_income",
            "capex",
            "free_cash_flow",
            "ending_equity",
        ),
        reconciliation_requirements=(
            "all_material_business_blocks_reconcile_to_consolidated_baseline",
            "ds_memory_view_does_not_stand_in_for_total_company_earnings",
            "quarterly_model_reconciles_to_annual_view",
            "cash_flow_and_equity_roll_forward_reconcile",
        ),
        invalidation_requirements=(
            "memory_price_reversal",
            "hbm_qualification_or_yield_failure",
            "foundry_loss_persistence_or_customer_ramp_failure",
            "mobile_or_consumer_demand_break",
            "ai_memory_demand_break",
        ),
    ),
}


@dataclass(frozen=True)
class ModelBlockCertification:
    block_id: str
    baseline_certified: bool
    forward_drivers_certified: bool
    output_method_certified: bool
    source_vintage_certified: bool


@dataclass(frozen=True)
class IssuerForwardModelCertification:
    ticker: str
    horizon_quarters: int
    block_certifications: tuple[ModelBlockCertification, ...]
    company_reconciliation_certified: bool
    model_version_frozen: bool
    decision_score_enabled: bool = False


@dataclass(frozen=True)
class IssuerForwardModelReadiness:
    ticker: str
    status: str
    ready_blocks: int
    required_blocks: int
    blockers: tuple[str, ...]
    internal_forward_model_certified: bool
    numeric_forecast_enabled: bool
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"available", "blocked"}:
            raise ValueError("Forward model readiness status is invalid")
        if self.internal_forward_model_certified != self.numeric_forecast_enabled:
            raise ValueError("Certified internal model and numeric forecast readiness must agree")
        if self.decision_score_enabled:
            raise ValueError("Forward operating model readiness must remain non-scoring")


def evaluate_issuer_forward_model_readiness(
    certification: IssuerForwardModelCertification,
) -> IssuerForwardModelReadiness:
    if certification.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
        raise ValueError(f"Forward model contract not registered: {certification.ticker}")
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[certification.ticker]
    lower, upper = contract.model_horizon_quarters
    if certification.horizon_quarters < lower or certification.horizon_quarters > upper:
        horizon_valid = False
    else:
        horizon_valid = True

    by_block = {item.block_id: item for item in certification.block_certifications}
    blockers: list[str] = []
    ready_blocks = 0
    for block in contract.blocks:
        item = by_block.get(block.block_id)
        if item is None:
            blockers.append(f"block_missing:{block.block_id}")
            continue
        block_ready = (
            item.baseline_certified
            and item.forward_drivers_certified
            and item.output_method_certified
            and item.source_vintage_certified
        )
        if block_ready:
            ready_blocks += 1
        else:
            if not item.baseline_certified:
                blockers.append(f"baseline_not_certified:{block.block_id}")
            if not item.forward_drivers_certified:
                blockers.append(f"forward_drivers_not_certified:{block.block_id}")
            if not item.output_method_certified:
                blockers.append(f"output_method_not_certified:{block.block_id}")
            if not item.source_vintage_certified:
                blockers.append(f"source_vintage_not_certified:{block.block_id}")
    extra = set(by_block) - {block.block_id for block in contract.blocks}
    if extra:
        blockers.append("unexpected_blocks:" + ",".join(sorted(extra)))
    if not horizon_valid:
        blockers.append("model_horizon_outside_contract")
    if not certification.company_reconciliation_certified:
        blockers.append("company_reconciliation_not_certified")
    if not certification.model_version_frozen:
        blockers.append("model_version_not_frozen")

    ready = (
        ready_blocks == len(contract.blocks)
        and not blockers
        and horizon_valid
        and certification.company_reconciliation_certified
        and certification.model_version_frozen
    )
    return IssuerForwardModelReadiness(
        ticker=certification.ticker,
        status="available" if ready else "blocked",
        ready_blocks=ready_blocks,
        required_blocks=len(contract.blocks),
        blockers=tuple(blockers),
        internal_forward_model_certified=ready,
        numeric_forecast_enabled=ready,
        decision_score_enabled=False,
    )


__all__ = [
    "SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS",
    "ForwardModelBlock",
    "IssuerForwardModelCertification",
    "IssuerForwardModelContract",
    "IssuerForwardModelReadiness",
    "ModelBlockCertification",
    "evaluate_issuer_forward_model_readiness",
]
