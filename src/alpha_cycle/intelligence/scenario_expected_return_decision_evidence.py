"""Map live evidence into sector-specific scenario/expected-return readiness."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from alpha_cycle.intelligence.scenario_expected_return import (
    SECTOR_SCENARIO_DEFINITIONS,
    ScenarioReadinessInputs,
    evaluate_scenario_expected_return_readiness,
)

SEMICONDUCTOR_TICKERS = {"000660", "005930"}


@dataclass(frozen=True)
class ScenarioExpectedReturnDecisionEvidence:
    rows: pd.DataFrame
    decision_score_enabled: bool = False
    price_range_enabled: bool = False
    expected_return_enabled: bool = False

    def __post_init__(self) -> None:
        if self.rows.empty:
            raise ValueError("Scenario expected-return decision evidence cannot be empty")
        if self.decision_score_enabled or self.price_range_enabled or self.expected_return_enabled:
            raise ValueError("Current Scenario/Expected Return v1 must remain readiness-only")


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes"}


def _current_price_available(row: dict[str, object]) -> bool:
    for column in ("current_price", "last_price", "market_price"):
        if column not in row:
            continue
        numeric = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
        if not pd.isna(numeric) and float(numeric) > 0:
            return True
    return False


def _semiconductor_drivers_available(row: dict[str, object]) -> bool:
    structural_required = (
        "structural_hbm_demand_mix_status",
        "structural_hbm_capacity_yield_status",
        "structural_competitive_position_status",
        "structural_end_demand_status",
        "structural_memory_pricing_status",
    )
    if any(str(row.get(column, "missing")) != "available" for column in structural_required):
        return False
    transmission_ready = _bool(row.get("semiconductor_transmission_history_ready"))
    return transmission_ready


def build_scenario_expected_return_decision_evidence(
    scorecards: pd.DataFrame,
) -> ScenarioExpectedReturnDecisionEvidence:
    if scorecards.empty or "ticker" not in scorecards.columns:
        raise ValueError("Scenario Expected Return v1 requires scorecards with ticker")
    rows: list[dict[str, object]] = []
    for raw_value in scorecards.to_dict(orient="records"):
        row = {str(key): value for key, value in raw_value.items()}
        ticker = str(row["ticker"]).strip().zfill(6)
        if ticker not in SEMICONDUCTOR_TICKERS:
            continue
        internal_forward_certified = str(
            row.get("expectation_gap_internal_forward_view_status", "")
        ) == "certified_forward_operating_view"
        expectation_level_certified = str(
            row.get("expectation_gap_expectation_level_status", "")
        ) == "available"
        catalyst_timing = int(
            pd.to_numeric(
                pd.Series([row.get("future_certified_event_count", 0)]), errors="coerce"
            ).fillna(0).iloc[0]
        ) > 0
        valuation_anchor_certified = _bool(row.get("scenario_valuation_anchor_certified"))
        forward_horizon_certified = _bool(row.get("scenario_forward_horizon_certified"))
        inputs = ScenarioReadinessInputs(
            sector_id="semiconductor",
            current_price_available=_current_price_available(row),
            internal_forward_model_certified=internal_forward_certified,
            forward_horizon_certified=forward_horizon_certified,
            required_operating_drivers_available=_semiconductor_drivers_available(row),
            valuation_anchor_certified=valuation_anchor_certified,
            catalyst_timing_available=catalyst_timing,
            market_expectation_level_certified=expectation_level_certified,
        )
        readiness = evaluate_scenario_expected_return_readiness(inputs)
        definition = SECTOR_SCENARIO_DEFINITIONS["semiconductor"]
        rows.append(
            {
                "ticker": ticker,
                "scenario_sector_id": readiness.sector_id,
                "scenario_operating_view_status": readiness.scenario_operating_view_status,
                "scenario_valuation_range_status": readiness.valuation_range_status,
                "scenario_expected_return_status": readiness.expected_return_status,
                "scenario_expectation_gap_context_status": readiness.expectation_gap_context_status,
                "scenario_blockers_json": json.dumps(list(readiness.blockers), ensure_ascii=False),
                "scenario_operating_drivers_json": json.dumps(
                    list(definition.operating_drivers), ensure_ascii=False
                ),
                "scenario_valuation_anchors_json": json.dumps(
                    list(definition.valuation_anchors), ensure_ascii=False
                ),
                "scenario_invalidation_drivers_json": json.dumps(
                    list(definition.invalidation_drivers), ensure_ascii=False
                ),
                "scenario_probabilities_enabled": False,
                "scenario_price_range_enabled": readiness.price_range_enabled,
                "scenario_expected_return_enabled": readiness.expected_return_enabled,
                "decision_score_enabled": False,
            }
        )
    frame = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    if frame.empty:
        raise ValueError("Scenario Expected Return v1 found no semiconductor tickers")
    return ScenarioExpectedReturnDecisionEvidence(rows=frame)


def append_scenario_expected_return_report(
    report: str,
    evidence: ScenarioExpectedReturnDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Scenario / Expected Return v1 (readiness·비점수)",
        "",
        "- Bull/Base/Bear driver는 산업별로 다르게 정의하며 확률을 근거 없이 만들지 않습니다.",
        "- 현재 반도체는 certified internal forward model·valuation anchor가 없으므로 price range/expected return을 산출하지 않습니다.",
        "- historical P/B/ROE와 industry transmission은 중요한 관측근거지만 그 자체를 forward fair-value anchor로 승격하지 않습니다.",
        "",
        "| 종목 | operating scenario | valuation range | expected return | expectation-gap context | price range enabled | 상태 |",
        "|---|---|---|---|---|---|---|",
    ]
    for raw in evidence.rows.to_dict(orient="records"):
        blockers = json.loads(str(raw["scenario_blockers_json"]))
        lines.append(
            f"| {raw['ticker']} | {raw['scenario_operating_view_status']} | "
            f"{raw['scenario_valuation_range_status']} | {raw['scenario_expected_return_status']} | "
            f"{raw['scenario_expectation_gap_context_status']} | "
            f"{raw['scenario_price_range_enabled']} | blocked={len(blockers)} |"
        )
        lines.append("  - blockers: " + ", ".join(str(item) for item in blockers))
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ScenarioExpectedReturnDecisionEvidence",
    "append_scenario_expected_return_report",
    "build_scenario_expected_return_decision_evidence",
]
