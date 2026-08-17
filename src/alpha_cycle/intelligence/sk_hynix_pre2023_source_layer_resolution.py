"""Resolve pre-2023 SK hynix source layers without forcing them into the current model.

The matrix joins three independently verified questions for 2021Q1-Q3 and 2022Q1-Q3:
company-level profitability, direct product-revenue availability, and issuer ASP/shipment
language. It is deliberately a source-resolution artifact, not a training-panel builder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_pre2023_cycle_driver_source_claims import (
    Pre2023CycleDriverPeriodProfile,
    profile_pre2023_cycle_driver_sources,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    ProductRevenueSourceClosurePeriod,
    audit_pre2023_product_revenue_sources,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_company_probe import (
    DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_COMPANY_PROBE_STATUS = (
    "skhynix_historical_expansion_company_profitability_probe_completed"
)


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Pre-2023 source resolution {label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _latest_company_probe(path: Path) -> dict[str, object]:
    pointer = path / "latest_company_profitability_probe.json"
    try:
        raw: object = json.loads(pointer.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Pre-2023 company probe pointer is missing: {pointer}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Pre-2023 company probe pointer is invalid JSON") from exc
    payload = _mapping(raw, "company probe")
    if payload.get("status") != _COMPANY_PROBE_STATUS:
        raise ValueError("Pre-2023 company probe status is invalid")
    return payload


@dataclass(frozen=True)
class VerifiedCompanyProfitabilityConstraint:
    period_id: str
    rcept_no: str
    revenue_krw: int
    cost_of_sales_krw: int
    gross_profit_krw: int
    gross_margin_percent: float
    raw_payload_sha256: str
    raw_payload_path: str
    raw_payload_hash_verified: bool = True
    accounting_identity_verified: bool = True
    current_retrieval_historical_source_fact: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    product_profitability_source_fact: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 company constraint period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Pre-2023 company constraint receipt is invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("Pre-2023 company constraint accounting identity failed")
        if len(self.raw_payload_sha256) != 64:
            raise ValueError("Pre-2023 company constraint raw hash is invalid")
        if not self.raw_payload_hash_verified or not self.accounting_identity_verified:
            raise ValueError("Pre-2023 company constraint verification is incomplete")
        if (
            not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.product_profitability_source_fact
        ):
            raise ValueError("Pre-2023 company constraint exceeded trust boundary")


def _company_constraints(root: Path) -> dict[str, VerifiedCompanyProfitabilityConstraint]:
    payload = _latest_company_probe(root)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Pre-2023 company probe results must be an array")
    constraints: dict[str, VerifiedCompanyProfitabilityConstraint] = {}
    for raw_result in raw_results:
        result = _mapping(raw_result, "company probe result")
        if result.get("success") is not True:
            continue
        period_id = str(result.get("period_id", ""))
        observation = _mapping(result.get("observation"), f"company observation {period_id}")
        raw_path = Path(str(result.get("raw_payload_path", "")))
        try:
            raw_payload: object = json.loads(raw_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Pre-2023 company raw payload cannot be replayed: {period_id}"
            ) from exc
        expected_sha = str(observation.get("raw_payload_sha256", ""))
        if _sha_payload(raw_payload) != expected_sha:
            raise ValueError(f"Pre-2023 company raw payload hash mismatch: {period_id}")
        constraint = VerifiedCompanyProfitabilityConstraint(
            period_id=period_id,
            rcept_no=str(observation.get("rcept_no", "")),
            revenue_krw=int(str(observation.get("revenue_krw", "0"))),
            cost_of_sales_krw=int(str(observation.get("cost_of_sales_krw", "0"))),
            gross_profit_krw=int(str(observation.get("gross_profit_krw", "0"))),
            gross_margin_percent=float(str(observation.get("gross_margin_percent", "nan"))),
            raw_payload_sha256=expected_sha,
            raw_payload_path=str(raw_path.resolve()),
        )
        constraints[period_id] = constraint
    return constraints


@dataclass(frozen=True)
class Pre2023SourceLayerResolutionPeriod:
    period_id: str
    company_profitability_constraint_verified: bool
    product_revenue_source_state: str
    aggregate_product_bucket_witness_count: int
    direct_product_revenue_candidate_count: int
    cycle_driver_source_state: str
    cycle_driver_claim_count: int
    source_language_four_field_coverage: bool
    existing_product_profitability_training_row_eligible: bool = False
    synthetic_product_allocation_allowed: bool = False
    numeric_driver_point_imputation_allowed: bool = False
    alternative_model_fit_allowed: bool = False
    holdout_evaluation_allowed: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 source-resolution period is unsupported")
        if self.product_revenue_source_state not in {
            "aggregate_only_observed",
            "direct_candidate_requires_review",
            "no_revenue_witness_observed",
        }:
            raise ValueError("Pre-2023 product-revenue source state is invalid")
        if self.cycle_driver_source_state not in {
            "four_field_source_language_coverage",
            "partial_source_language_coverage",
            "no_driver_claims_observed",
        }:
            raise ValueError("Pre-2023 cycle-driver source state is invalid")
        if self.aggregate_product_bucket_witness_count < 0:
            raise ValueError("Pre-2023 aggregate witness count is invalid")
        if self.direct_product_revenue_candidate_count < 0 or self.cycle_driver_claim_count < 0:
            raise ValueError("Pre-2023 source-resolution counts are invalid")
        forbidden = (
            self.existing_product_profitability_training_row_eligible,
            self.synthetic_product_allocation_allowed,
            self.numeric_driver_point_imputation_allowed,
            self.alternative_model_fit_allowed,
            self.holdout_evaluation_allowed,
        )
        if any(forbidden):
            raise ValueError("Pre-2023 source resolution exceeded trust boundary")


@dataclass(frozen=True)
class Pre2023SourceLayerResolution:
    evidence_id: str
    periods: tuple[Pre2023SourceLayerResolutionPeriod, ...]
    company_constraint_verified_count: int
    aggregate_only_product_revenue_count: int
    direct_product_revenue_candidate_count: int
    four_field_source_language_count: int
    current_model_training_row_eligible_count: int
    synthetic_product_allocation_allowed: bool = False
    numeric_driver_point_imputation_allowed: bool = False
    alternative_model_fit_allowed: bool = False
    holdout_evaluation_allowed: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Pre-2023 source-resolution evidence id must be SHA-256")
        if tuple(item.period_id for item in self.periods) != _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 source-resolution periods are incomplete")
        if self.company_constraint_verified_count != sum(
            item.company_profitability_constraint_verified for item in self.periods
        ):
            raise ValueError("Pre-2023 company constraint count is inconsistent")
        if self.aggregate_only_product_revenue_count != sum(
            item.product_revenue_source_state == "aggregate_only_observed"
            for item in self.periods
        ):
            raise ValueError("Pre-2023 aggregate-only count is inconsistent")
        if self.direct_product_revenue_candidate_count != sum(
            item.direct_product_revenue_candidate_count > 0 for item in self.periods
        ):
            raise ValueError("Pre-2023 direct-candidate period count is inconsistent")
        if self.four_field_source_language_count != sum(
            item.source_language_four_field_coverage for item in self.periods
        ):
            raise ValueError("Pre-2023 four-field language count is inconsistent")
        if self.current_model_training_row_eligible_count != 0:
            raise ValueError("Pre-2023 source resolution cannot promote current model rows")
        if (
            self.synthetic_product_allocation_allowed
            or self.numeric_driver_point_imputation_allowed
            or self.alternative_model_fit_allowed
            or self.holdout_evaluation_allowed
        ):
            raise ValueError("Pre-2023 source resolution exceeded model boundary")


def _product_state(item: ProductRevenueSourceClosurePeriod) -> str:
    if item.direct_separable_candidate_count > 0:
        return "direct_candidate_requires_review"
    if item.aggregate_only_observed:
        return "aggregate_only_observed"
    return "no_revenue_witness_observed"


def _cycle_state(item: Pre2023CycleDriverPeriodProfile) -> str:
    if item.source_language_four_field_coverage:
        return "four_field_source_language_coverage"
    if item.claim_count > 0:
        return "partial_source_language_coverage"
    return "no_driver_claims_observed"


def build_pre2023_source_layer_resolution(
    *,
    product_probe_output: str | Path = DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
    company_probe_output: str | Path = DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT,
) -> tuple[Pre2023SourceLayerResolution, dict[str, VerifiedCompanyProfitabilityConstraint]]:
    company = _company_constraints(Path(company_probe_output))
    product = {
        item.period_id: item
        for item in audit_pre2023_product_revenue_sources(output=product_probe_output)
    }
    cycle = {
        item.period_id: item
        for item in profile_pre2023_cycle_driver_sources(output=product_probe_output)
    }
    periods = tuple(
        Pre2023SourceLayerResolutionPeriod(
            period_id=period_id,
            company_profitability_constraint_verified=period_id in company,
            product_revenue_source_state=_product_state(product[period_id]),
            aggregate_product_bucket_witness_count=(
                product[period_id].aggregate_bucket_witness_count
            ),
            direct_product_revenue_candidate_count=(
                product[period_id].direct_separable_candidate_count
            ),
            cycle_driver_source_state=_cycle_state(cycle[period_id]),
            cycle_driver_claim_count=cycle[period_id].claim_count,
            source_language_four_field_coverage=(
                cycle[period_id].source_language_four_field_coverage
            ),
        )
        for period_id in _EXPECTED_PERIODS
    )
    stable = {
        "periods": [item.__dict__ for item in periods],
        "company_raw_hashes": {
            period_id: item.raw_payload_sha256 for period_id, item in sorted(company.items())
        },
        "synthetic_product_allocation_allowed": False,
        "numeric_driver_point_imputation_allowed": False,
        "alternative_model_fit_allowed": False,
    }
    resolution = Pre2023SourceLayerResolution(
        evidence_id=_sha_payload(stable),
        periods=periods,
        company_constraint_verified_count=sum(
            item.company_profitability_constraint_verified for item in periods
        ),
        aggregate_only_product_revenue_count=sum(
            item.product_revenue_source_state == "aggregate_only_observed" for item in periods
        ),
        direct_product_revenue_candidate_count=sum(
            item.direct_product_revenue_candidate_count > 0 for item in periods
        ),
        four_field_source_language_count=sum(
            item.source_language_four_field_coverage for item in periods
        ),
        current_model_training_row_eligible_count=0,
    )
    return resolution, company


__all__ = [
    "Pre2023SourceLayerResolution",
    "Pre2023SourceLayerResolutionPeriod",
    "VerifiedCompanyProfitabilityConstraint",
    "build_pre2023_source_layer_resolution",
]
