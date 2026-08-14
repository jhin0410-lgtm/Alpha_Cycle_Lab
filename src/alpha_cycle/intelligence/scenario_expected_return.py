"""Sector-specific Bull/Base/Bear scenario and expected-return readiness.

Scenario mechanics are shared, but operating drivers are sector specific.  Price
ranges and expected returns remain disabled until a certified internal forward
operating model and a defensible valuation anchor exist.  The framework never
fabricates scenario probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectorScenarioDefinition:
    sector_id: str
    operating_drivers: tuple[str, ...]
    valuation_anchors: tuple[str, ...]
    invalidation_drivers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.sector_id.strip():
            raise ValueError("Scenario sector_id cannot be blank")
        if not self.operating_drivers or not self.valuation_anchors or not self.invalidation_drivers:
            raise ValueError("Scenario definition requires drivers, valuation anchors, invalidations")


SECTOR_SCENARIO_DEFINITIONS: dict[str, SectorScenarioDefinition] = {
    "semiconductor": SectorScenarioDefinition(
        "semiconductor",
        (
            "dram_nand_price_direction_and_level",
            "hbm_volume_and_product_mix",
            "hbm_capacity_yield_and_packaging",
            "memory_inventory_and_utilization",
            "ai_server_pc_mobile_demand",
            "supplier_capex_and_supply_growth",
            "fx",
            "segment_margin_and_operating_leverage",
        ),
        ("cycle_normalized_pb_roe", "cycle_normalized_pe", "fcf_yield"),
        (
            "memory_price_reversal",
            "hbm_qualification_or_yield_failure",
            "inventory_reaccumulation",
            "ai_capex_demand_break",
        ),
    ),
    "defense": SectorScenarioDefinition(
        "defense",
        (
            "export_award_pipeline",
            "backlog_delivery_schedule",
            "production_capacity",
            "export_product_mix",
            "contract_margin",
            "fx",
            "working_capital",
        ),
        ("forward_pe", "ev_ebitda", "backlog_and_fcf_supported_multiple"),
        ("major_bid_loss", "delivery_delay", "export_license_failure", "margin_dilution"),
    ),
    "shipbuilding": SectorScenarioDefinition(
        "shipbuilding",
        (
            "newbuild_price",
            "order_intake",
            "orderbook_delivery_mix",
            "low_price_backlog_burnoff",
            "yard_utilization",
            "steel_plate_and_labor_cost",
            "fx",
        ),
        ("forward_pe", "ev_ebitda", "normalized_margin_multiple"),
        ("newbuild_price_reversal", "order_collapse", "cost_inflation", "schedule_delay"),
    ),
    "power_equipment": SectorScenarioDefinition(
        "power_equipment",
        (
            "grid_capex",
            "book_to_bill",
            "backlog_conversion",
            "lead_time_and_pricing",
            "capacity_expansion",
            "copper_input_cost",
            "regional_mix_and_tariffs",
        ),
        ("forward_pe", "ev_ebitda", "fcf_yield"),
        ("book_to_bill_break", "lead_time_normalization", "pricing_reversal", "capacity_execution_failure"),
    ),
    "nuclear": SectorScenarioDefinition(
        "nuclear",
        (
            "project_award_probability",
            "licensing_milestones",
            "financing_and_eca",
            "epc_revenue_timing",
            "local_content",
            "cost_overrun_and_delay",
        ),
        ("probability_weighted_project_value", "forward_pe", "ev_ebitda"),
        ("license_failure", "award_loss", "financing_failure", "material_cost_overrun"),
    ),
    "construction": SectorScenarioDefinition(
        "construction",
        (
            "housing_presales",
            "domestic_and_overseas_backlog",
            "pf_credit_conditions",
            "guarantees_and_contingent_liabilities",
            "materials_and_labor_cost",
            "project_margin_conversion",
            "working_capital_and_unbilled_receivables",
        ),
        ("normalized_pb_roe", "forward_pe", "ev_ebitda"),
        ("pf_credit_event", "cost_overrun", "presale_failure", "guarantee_crystallization"),
    ),
    "battery": SectorScenarioDefinition(
        "battery",
        (
            "ev_demand",
            "inventory",
            "utilization",
            "lithium_nickel_input_cost",
            "asp_and_product_mix",
            "chemistry_mix",
            "customer_volume",
            "capex_and_jv_ramp",
            "subsidy_and_tariff",
        ),
        ("ev_ebitda", "forward_pe", "normalized_fcf_yield"),
        ("ev_demand_break", "inventory_reaccumulation", "utilization_collapse", "policy_support_reversal"),
    ),
    "auto": SectorScenarioDefinition(
        "auto",
        (
            "global_unit_demand",
            "regional_mix",
            "pricing_and_incentives",
            "fx",
            "raw_material_cost",
            "ice_hybrid_ev_mix",
            "warranty_cost",
            "capacity_and_inventory",
        ),
        ("forward_pe", "normalized_pb_roe", "fcf_yield"),
        ("incentive_spike", "inventory_build", "fx_reversal", "warranty_cost_shock"),
    ),
    "bio": SectorScenarioDefinition(
        "bio",
        (
            "clinical_or_regulatory_probability",
            "launch_timing",
            "eligible_patient_population",
            "price_and_reimbursement",
            "market_share",
            "manufacturing_capacity",
            "cash_burn",
        ),
        ("probability_adjusted_npv", "ev_sales_after_commercialization"),
        ("trial_failure", "regulatory_rejection", "reimbursement_failure", "liquidity_shortfall"),
    ),
    "internet_platform": SectorScenarioDefinition(
        "internet_platform",
        (
            "mau_and_engagement",
            "ad_or_commerce_take_rate",
            "arpu",
            "traffic_acquisition_cost",
            "ai_infrastructure_cost",
            "regulation",
            "operating_margin",
        ),
        ("forward_pe", "ev_ebitda", "fcf_yield"),
        ("engagement_decline", "take_rate_pressure", "regulatory_intervention", "cost_inflation"),
    ),
    "robotics": SectorScenarioDefinition(
        "robotics",
        (
            "order_intake",
            "backlog",
            "customer_capex",
            "component_cost",
            "deployment_rate",
            "service_or_software_mix",
            "capacity",
        ),
        ("ev_sales", "ev_ebitda_when_profitable", "forward_pe_when_mature"),
        ("order_cancellation", "customer_capex_cut", "deployment_delay", "unit_economics_deterioration"),
    ),
}


@dataclass(frozen=True)
class ScenarioReadinessInputs:
    sector_id: str
    current_price_available: bool
    internal_forward_model_certified: bool
    forward_horizon_certified: bool
    required_operating_drivers_available: bool
    valuation_anchor_certified: bool
    catalyst_timing_available: bool
    market_expectation_level_certified: bool


@dataclass(frozen=True)
class ScenarioExpectedReturnReadiness:
    sector_id: str
    scenario_operating_view_status: str
    valuation_range_status: str
    expected_return_status: str
    expectation_gap_context_status: str
    blockers: tuple[str, ...]
    scenario_probabilities_enabled: bool = False
    price_range_enabled: bool = False
    expected_return_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        allowed = {"available", "blocked"}
        if (
            self.scenario_operating_view_status not in allowed
            or self.valuation_range_status not in allowed
            or self.expected_return_status not in allowed
            or self.expectation_gap_context_status not in allowed
        ):
            raise ValueError("Scenario readiness status is invalid")
        if self.scenario_probabilities_enabled:
            raise ValueError("Scenario probabilities require a separately supported probability model")
        if self.decision_score_enabled:
            raise ValueError("Scenario readiness must remain non-scoring")
        if self.price_range_enabled and self.valuation_range_status != "available":
            raise ValueError("Price range cannot be enabled without valuation readiness")
        if self.expected_return_enabled and self.expected_return_status != "available":
            raise ValueError("Expected return cannot be enabled while blocked")


def evaluate_scenario_expected_return_readiness(
    inputs: ScenarioReadinessInputs,
) -> ScenarioExpectedReturnReadiness:
    if inputs.sector_id not in SECTOR_SCENARIO_DEFINITIONS:
        raise ValueError(f"Scenario definition is not registered: {inputs.sector_id}")
    operating_requirements = {
        "internal_forward_model_not_certified": inputs.internal_forward_model_certified,
        "forward_horizon_not_certified": inputs.forward_horizon_certified,
        "required_operating_drivers_missing": inputs.required_operating_drivers_available,
    }
    operating_blockers = tuple(
        blocker for blocker, satisfied in operating_requirements.items() if not satisfied
    )
    operating_available = not operating_blockers
    valuation_available = operating_available and inputs.valuation_anchor_certified
    expected_return_available = valuation_available and inputs.current_price_available
    expectation_gap_context_available = (
        operating_available and inputs.market_expectation_level_certified
    )
    blockers = list(operating_blockers)
    if not inputs.valuation_anchor_certified:
        blockers.append("valuation_anchor_not_certified")
    if not inputs.current_price_available:
        blockers.append("current_price_missing")
    if not inputs.catalyst_timing_available:
        blockers.append("catalyst_timing_missing")
    if not inputs.market_expectation_level_certified:
        blockers.append("market_expectation_level_not_certified")
    return ScenarioExpectedReturnReadiness(
        sector_id=inputs.sector_id,
        scenario_operating_view_status="available" if operating_available else "blocked",
        valuation_range_status="available" if valuation_available else "blocked",
        expected_return_status="available" if expected_return_available else "blocked",
        expectation_gap_context_status=(
            "available" if expectation_gap_context_available else "blocked"
        ),
        blockers=tuple(dict.fromkeys(blockers)),
        scenario_probabilities_enabled=False,
        price_range_enabled=valuation_available,
        expected_return_enabled=expected_return_available,
        decision_score_enabled=False,
    )


__all__ = [
    "SECTOR_SCENARIO_DEFINITIONS",
    "ScenarioExpectedReturnReadiness",
    "ScenarioReadinessInputs",
    "SectorScenarioDefinition",
    "evaluate_scenario_expected_return_readiness",
]
