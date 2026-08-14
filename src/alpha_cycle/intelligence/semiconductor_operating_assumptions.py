"""Internal Bull/Base/Bear operating assumptions for semiconductor forward models.

Source evidence and model assumptions are different objects.  This module records the
numeric assumptions Alpha Cycle chooses to make after reviewing source evidence.  An
assumption is never represented as a source fact, scenario probabilities remain disabled,
and assumption completeness alone cannot certify an issuer forward forecast.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
)

_ALLOWED_SCENARIOS = frozenset({"bear", "base", "bull"})
_ALLOWED_METHOD_STATUS = frozenset({"draft", "documented", "observationally_calibrated"})


@dataclass(frozen=True)
class OperatingAssumption:
    assumption_id: str
    ticker: str
    block_id: str
    driver_id: str
    scenario: str
    quarter_index: int
    value: float
    unit: str
    method_id: str
    method_version: str
    method_status: str
    method_version_frozen: bool
    supporting_evidence_ids: tuple[str, ...]
    supporting_evidence_verified: bool
    rationale: str
    invalidation_condition: str
    evaluation_date: date
    model_use_ready: bool
    source_fact: bool = False
    scenario_probability_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.assumption_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.assumption_id
        ):
            raise ValueError("Operating assumption_id must be SHA-256")
        if self.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
            raise ValueError(f"Operating assumption issuer is not registered: {self.ticker}")
        if self.scenario not in _ALLOWED_SCENARIOS:
            raise ValueError("Operating assumption scenario is invalid")
        if self.method_status not in _ALLOWED_METHOD_STATUS:
            raise ValueError("Operating assumption method_status is invalid")
        if not math.isfinite(self.value):
            raise ValueError("Operating assumption value must be finite")
        if not self.unit.strip() or not self.method_id.strip() or not self.method_version.strip():
            raise ValueError("Operating assumption unit/method identity cannot be blank")
        if not self.rationale.strip() or not self.invalidation_condition.strip():
            raise ValueError("Operating assumption requires rationale and invalidation")
        if not self.supporting_evidence_ids:
            raise ValueError("Operating assumption requires supporting evidence")
        if any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in self.supporting_evidence_ids
        ):
            raise ValueError("Operating assumption evidence IDs must be SHA-256")
        if self.source_fact:
            raise ValueError("Internal operating assumption cannot be labeled a source fact")
        if self.scenario_probability_enabled:
            raise ValueError("Operating assumption layer cannot enable scenario probabilities")
        if self.decision_score_enabled:
            raise ValueError("Operating assumptions must remain non-scoring")
        if self.model_use_ready and (
            self.method_status != "observationally_calibrated"
            or not self.method_version_frozen
            or not self.supporting_evidence_verified
        ):
            raise ValueError("Model-use-ready assumptions require calibrated frozen verified method")


@dataclass(frozen=True)
class OperatingAssumptionPack:
    pack_id: str
    evaluation_date: date
    horizon_quarters: int
    assumptions: tuple[OperatingAssumption, ...]
    scenario_coverage: pd.DataFrame
    scenario_probabilities_enabled: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.pack_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.pack_id
        ):
            raise ValueError("Operating assumption pack_id must be SHA-256")
        if not self.assumptions or self.scenario_coverage.empty:
            raise ValueError("Operating assumption pack requires assumptions and coverage")
        if self.scenario_probabilities_enabled:
            raise ValueError("Operating assumption pack cannot enable scenario probabilities")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Operating assumption pack cannot enable forecast/scoring")


def _sha(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _driver_registered(ticker: str, block_id: str, driver_id: str) -> bool:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker]
    for block in contract.blocks:
        if block.block_id == block_id:
            return driver_id in block.required_forward_drivers
    return False


def validate_operating_assumption(
    raw: dict[str, object],
    *,
    evaluation_date: date,
    horizon_quarters: int,
    verified_evidence_ids: set[str] | None = None,
) -> OperatingAssumption:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    if ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
        raise ValueError(f"Operating assumption issuer is not registered: {ticker}")
    lower, upper = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker].model_horizon_quarters
    if not lower <= horizon_quarters <= upper:
        raise ValueError(f"Operating assumption horizon outside issuer contract: {ticker}")
    block_id = str(raw.get("block_id", "")).strip()
    driver_id = str(raw.get("driver_id", "")).strip()
    if not _driver_registered(ticker, block_id, driver_id):
        raise ValueError(
            f"Operating assumption driver is outside issuer block contract: "
            f"{ticker}/{block_id}/{driver_id}"
        )
    scenario = str(raw.get("scenario", "")).strip().casefold()
    if scenario not in _ALLOWED_SCENARIOS:
        raise ValueError("Operating assumption scenario is invalid")
    quarter_index = int(raw.get("quarter_index", 0))
    if not 1 <= quarter_index <= horizon_quarters:
        raise ValueError("Operating assumption quarter_index is outside model horizon")
    value = float(raw.get("value", "nan"))
    unit = str(raw.get("unit", "")).strip()
    method_id = str(raw.get("method_id", "")).strip()
    method_version = str(raw.get("method_version", "")).strip()
    method_status = str(raw.get("method_status", "draft")).strip()
    method_version_frozen = bool(raw.get("method_version_frozen", False))
    raw_support = raw.get("supporting_evidence_ids", [])
    if not isinstance(raw_support, list):
        raise ValueError("Operating assumption supporting_evidence_ids must be an array")
    supporting_ids = tuple(dict.fromkeys(str(item).strip() for item in raw_support if str(item).strip()))
    known = verified_evidence_ids
    support_verified = bool(known is not None and supporting_ids and set(supporting_ids).issubset(known))
    rationale = str(raw.get("rationale", "")).strip()
    invalidation = str(raw.get("invalidation_condition", "")).strip()
    model_use_ready = bool(
        method_status == "observationally_calibrated"
        and method_version_frozen
        and support_verified
        and supporting_ids
    )
    payload: dict[str, object] = {
        "ticker": ticker,
        "block_id": block_id,
        "driver_id": driver_id,
        "scenario": scenario,
        "quarter_index": quarter_index,
        "value": value,
        "unit": unit,
        "method_id": method_id,
        "method_version": method_version,
        "method_status": method_status,
        "method_version_frozen": method_version_frozen,
        "supporting_evidence_ids": list(supporting_ids),
        "supporting_evidence_verified": support_verified,
        "rationale": rationale,
        "invalidation_condition": invalidation,
        "evaluation_date": evaluation_date.isoformat(),
        "model_use_ready": model_use_ready,
        "source_fact": False,
        "scenario_probability_enabled": False,
        "decision_score_enabled": False,
    }
    return OperatingAssumption(
        assumption_id=_sha(payload),
        ticker=ticker,
        block_id=block_id,
        driver_id=driver_id,
        scenario=scenario,
        quarter_index=quarter_index,
        value=value,
        unit=unit,
        method_id=method_id,
        method_version=method_version,
        method_status=method_status,
        method_version_frozen=method_version_frozen,
        supporting_evidence_ids=supporting_ids,
        supporting_evidence_verified=support_verified,
        rationale=rationale,
        invalidation_condition=invalidation,
        evaluation_date=evaluation_date,
        model_use_ready=model_use_ready,
    )


def _scenario_coverage(
    assumptions: tuple[OperatingAssumption, ...],
    *,
    horizon_quarters: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, contract in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.items():
        required_pairs = {
            (block.block_id, driver, quarter)
            for block in contract.blocks
            for driver in block.required_forward_drivers
            for quarter in range(1, horizon_quarters + 1)
        }
        for scenario in sorted(_ALLOWED_SCENARIOS):
            selected = [
                item
                for item in assumptions
                if item.ticker == ticker and item.scenario == scenario
            ]
            supplied_pairs = {
                (item.block_id, item.driver_id, item.quarter_index) for item in selected
            }
            ready_pairs = {
                (item.block_id, item.driver_id, item.quarter_index)
                for item in selected
                if item.model_use_ready
            }
            rows.append(
                {
                    "ticker": ticker,
                    "scenario": scenario,
                    "required_driver_quarter_count": len(required_pairs),
                    "supplied_driver_quarter_count": len(required_pairs & supplied_pairs),
                    "model_use_ready_driver_quarter_count": len(required_pairs & ready_pairs),
                    "assumption_coverage_complete": required_pairs.issubset(supplied_pairs),
                    "model_use_assumptions_complete": required_pairs.issubset(ready_pairs),
                    "scenario_probability_enabled": False,
                    "numeric_forecast_enabled": False,
                    "decision_score_enabled": False,
                }
            )
    return pd.DataFrame(rows).sort_values(["ticker", "scenario"], kind="stable").reset_index(
        drop=True
    )


def build_operating_assumption_pack(
    raw_assumptions: list[dict[str, object]],
    *,
    evaluation_date: date,
    horizon_quarters: int,
    verified_evidence_ids: set[str] | None = None,
) -> OperatingAssumptionPack:
    assumptions = tuple(
        validate_operating_assumption(
            raw,
            evaluation_date=evaluation_date,
            horizon_quarters=horizon_quarters,
            verified_evidence_ids=verified_evidence_ids,
        )
        for raw in raw_assumptions
    )
    if not assumptions:
        raise ValueError("Operating assumption pack requires assumptions")
    natural_keys = [
        (item.ticker, item.block_id, item.driver_id, item.scenario, item.quarter_index)
        for item in assumptions
    ]
    if len(set(natural_keys)) != len(natural_keys):
        raise ValueError("Operating assumption pack contains duplicate driver-quarter assumptions")
    coverage = _scenario_coverage(assumptions, horizon_quarters=horizon_quarters)
    payload: dict[str, object] = {
        "evaluation_date": evaluation_date.isoformat(),
        "horizon_quarters": horizon_quarters,
        "assumption_ids": [item.assumption_id for item in assumptions],
        "scenario_coverage": coverage.to_dict(orient="records"),
        "scenario_probabilities_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OperatingAssumptionPack(
        pack_id=_sha(payload),
        evaluation_date=evaluation_date,
        horizon_quarters=horizon_quarters,
        assumptions=assumptions,
        scenario_coverage=coverage,
    )


__all__ = [
    "OperatingAssumption",
    "OperatingAssumptionPack",
    "build_operating_assumption_pack",
    "validate_operating_assumption",
]
