"""Conditionally spend and immutably preserve the frozen SK hynix 2026Q1 holdout.

The holdout sources are not loaded unless the frozen 15-row training gate passes. The first
authorized evaluation is persisted and every later invocation must reproduce/reuse that
same result. The frozen v1 method cannot be refit after holdout exposure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import numpy as np

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    FrozenRegimeEstimationMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_training_fit import (
    RegimeTrainingFitResult,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_validation_protocol import (
    RegimeValidationProtocol,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    encode_direction_sign,
    load_product_certifications_for_historical_panel,
)

DEFAULT_REGIME_VALIDATION_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-regime-validation"
)
DEFAULT_REGIME_HOLDOUT_POINTER = DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_holdout_result.json"


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


@dataclass(frozen=True)
class RegimeHoldoutResult:
    evidence_id: str
    method_evidence_id: str
    training_fit_evidence_id: str
    holdout_period: str
    source_evaluation_date: date
    product_revenue_evidence_id: str
    company_profitability_evidence_id: str
    cycle_driver_evidence_id: str
    company_revenue_krw_million: float
    actual_gross_profit_krw_million: float
    model_prediction_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float
    model_beats_benchmark: bool
    company_product_revenue_reconciled: bool
    holdout_validation_passed: bool
    holdout_spent: bool = True
    immutable_result: bool = True
    refit_after_holdout_allowed: bool = False
    product_profitability_is_direct_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.method_evidence_id,
            self.training_fit_evidence_id,
            self.product_revenue_evidence_id,
            self.company_profitability_evidence_id,
            self.cycle_driver_evidence_id,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("Regime holdout evidence ids must be SHA-256")
        if self.holdout_period != "2026Q1":
            raise ValueError("Regime holdout period drifted")
        expected_better = self.model_absolute_error_krw_million < self.benchmark_absolute_error_krw_million
        if self.model_beats_benchmark != expected_better:
            raise ValueError("Regime holdout benchmark comparison is inconsistent")
        expected_pass = self.model_beats_benchmark and self.company_product_revenue_reconciled
        if self.holdout_validation_passed != expected_pass:
            raise ValueError("Regime holdout validation flag is inconsistent")
        if not self.holdout_spent or not self.immutable_result or self.refit_after_holdout_allowed:
            raise ValueError("Regime holdout immutability boundary drifted")
        if (
            self.product_profitability_is_direct_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Regime holdout opened downstream outputs")


def _payload(result: RegimeHoldoutResult) -> dict[str, object]:
    payload = asdict(result)
    payload["source_evaluation_date"] = result.source_evaluation_date.isoformat()
    return payload


def _result_from_payload(payload: dict[str, object]) -> RegimeHoldoutResult:
    return RegimeHoldoutResult(
        evidence_id=str(payload.get("evidence_id", "")),
        method_evidence_id=str(payload.get("method_evidence_id", "")),
        training_fit_evidence_id=str(payload.get("training_fit_evidence_id", "")),
        holdout_period=str(payload.get("holdout_period", "")),
        source_evaluation_date=date.fromisoformat(str(payload.get("source_evaluation_date", ""))),
        product_revenue_evidence_id=str(payload.get("product_revenue_evidence_id", "")),
        company_profitability_evidence_id=str(
            payload.get("company_profitability_evidence_id", "")
        ),
        cycle_driver_evidence_id=str(payload.get("cycle_driver_evidence_id", "")),
        company_revenue_krw_million=float(payload.get("company_revenue_krw_million", 0.0)),
        actual_gross_profit_krw_million=float(
            payload.get("actual_gross_profit_krw_million", 0.0)
        ),
        model_prediction_krw_million=float(payload.get("model_prediction_krw_million", 0.0)),
        model_absolute_error_krw_million=float(
            payload.get("model_absolute_error_krw_million", 0.0)
        ),
        benchmark_prediction_krw_million=float(
            payload.get("benchmark_prediction_krw_million", 0.0)
        ),
        benchmark_absolute_error_krw_million=float(
            payload.get("benchmark_absolute_error_krw_million", 0.0)
        ),
        model_beats_benchmark=payload.get("model_beats_benchmark") is True,
        company_product_revenue_reconciled=(
            payload.get("company_product_revenue_reconciled") is True
        ),
        holdout_validation_passed=payload.get("holdout_validation_passed") is True,
        holdout_spent=payload.get("holdout_spent") is True,
        immutable_result=payload.get("immutable_result") is True,
        refit_after_holdout_allowed=payload.get("refit_after_holdout_allowed") is True,
        product_profitability_is_direct_source_fact=(
            payload.get("product_profitability_is_direct_source_fact") is True
        ),
        numeric_forecast_enabled=payload.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=payload.get("fair_value_estimate_enabled") is True,
        target_price_enabled=payload.get("target_price_enabled") is True,
        decision_score_enabled=payload.get("decision_score_enabled") is True,
    )


def _reuse_existing(
    pointer: Path,
    method: FrozenRegimeEstimationMethod,
    training_fit: RegimeTrainingFitResult,
) -> RegimeHoldoutResult:
    wrapper = _object(pointer, "Regime holdout pointer")
    if wrapper.get("status") != "skhynix_product_profitability_regime_holdout_spent":
        raise ValueError("Regime holdout pointer status is invalid")
    if str(wrapper.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Regime holdout already spent under another frozen method")
    if str(wrapper.get("training_fit_evidence_id", "")) != training_fit.evidence_id:
        raise ValueError("Regime holdout already spent under another training fit")
    raw_result = wrapper.get("result")
    if not isinstance(raw_result, dict):
        raise ValueError("Regime holdout pointer result is invalid")
    payload = {str(key): value for key, value in cast(dict[object, object], raw_result).items()}
    if _sha({key: value for key, value in payload.items() if key != "evidence_id"}) != str(
        payload.get("evidence_id", "")
    ):
        raise ValueError("Regime holdout persisted result hash mismatch")
    return _result_from_payload(payload)


def spend_regime_holdout_once(
    method: FrozenRegimeEstimationMethod,
    protocol: RegimeValidationProtocol,
    training_fit: RegimeTrainingFitResult,
    *,
    source_evaluation_date: date,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
    output: str | Path = DEFAULT_REGIME_VALIDATION_OUTPUT,
) -> tuple[RegimeHoldoutResult, bool]:
    """Evaluate the sealed holdout once; return ``(result, reused_existing)``."""

    if protocol.method_evidence_id != method.evidence_id:
        raise ValueError("Regime holdout protocol/method binding diverged")
    if not training_fit.one_time_holdout_evaluation_ready:
        raise ValueError("Regime holdout cannot be loaded before the training gate passes")
    if training_fit.method_evidence_id != method.evidence_id:
        raise ValueError("Regime holdout training/method binding diverged")
    root = Path(output)
    pointer = root / "latest_holdout_result.json"
    if pointer.is_file():
        return _reuse_existing(pointer, method, training_fit), True

    # HOLDOUT SOURCE ACCESS STARTS ONLY AFTER THE GATE ABOVE.
    historical = load_historical_product_revenue_panel_evidence(
        historical_product_revenue_pointer,
        evaluation_date=source_evaluation_date,
    )
    products = load_product_certifications_for_historical_panel(
        historical,
        evaluation_date=source_evaluation_date,
    )
    company = load_quarterly_company_profitability_evidence(
        company_profitability_pointer,
        evaluation_date=source_evaluation_date,
    )
    cycle = load_sec_product_cycle_driver_support_evidence(
        cycle_driver_pointer,
        evaluation_date=source_evaluation_date,
    )
    period = method.holdout_period
    product = products.get(period)
    company_by_period = {item.period_id: item for item in company.observations}
    cycle_by_period = {item.period_id: item for item in cycle.observations}
    company_row = company_by_period.get(period)
    cycle_row = cycle_by_period.get(period)
    if product is None or company_row is None or cycle_row is None:
        raise ValueError("Regime holdout source layers are incomplete")

    product_total_krw = int(round(product.metrics.reported_company_revenue * 1_000_000.0))
    delta_krw = product_total_krw - company_row.revenue_krw
    reconciled = abs(delta_krw) <= protocol.company_revenue_reconciliation_tolerance_krw
    if not reconciled:
        raise ValueError("Regime holdout company/product revenue reconciliation failed")
    dram_asp = encode_direction_sign(cycle_row.dram_asp_usd_qoq_text).code
    dram_bit = encode_direction_sign(cycle_row.dram_bit_sales_volume_qoq_text).code
    nand_asp = encode_direction_sign(cycle_row.nand_asp_usd_qoq_text).code
    nand_bit = encode_direction_sign(cycle_row.nand_bit_sales_volume_qoq_text).code
    dram = float(product.metrics.dram_total)
    nand = float(product.metrics.nand_and_solutions)
    other = float(product.metrics.other_products_services)
    design = np.asarray(
        (
            dram,
            dram * dram_asp,
            dram * dram_bit,
            nand,
            nand * nand_asp,
            nand * nand_bit,
            other,
        ),
        dtype=float,
    )
    coefficients = np.asarray(training_fit.coefficients, dtype=float)
    model_prediction = float(design @ coefficients)
    actual = company_row.gross_profit_krw / 1_000_000.0
    company_revenue = company_row.revenue_krw / 1_000_000.0
    benchmark_prediction = training_fit.mean_training_gross_margin * company_revenue
    model_error = abs(actual - model_prediction)
    benchmark_error = abs(actual - benchmark_prediction)
    stable = {
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_fit.evidence_id,
        "holdout_period": period,
        "source_evaluation_date": source_evaluation_date.isoformat(),
        "product_revenue_evidence_id": product.evidence_id,
        "company_profitability_evidence_id": company.evidence_id,
        "cycle_driver_evidence_id": cycle.evidence_id,
        "company_revenue_krw_million": company_revenue,
        "actual_gross_profit_krw_million": actual,
        "model_prediction_krw_million": model_prediction,
        "model_absolute_error_krw_million": model_error,
        "benchmark_prediction_krw_million": benchmark_prediction,
        "benchmark_absolute_error_krw_million": benchmark_error,
        "model_beats_benchmark": model_error < benchmark_error,
        "company_product_revenue_reconciled": reconciled,
        "holdout_validation_passed": model_error < benchmark_error and reconciled,
        "holdout_spent": True,
        "immutable_result": True,
        "refit_after_holdout_allowed": False,
        "product_profitability_is_direct_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    result = RegimeHoldoutResult(evidence_id=_sha(stable), **stable)
    root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    directory = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__" + result.evidence_id[:12]
    )
    directory.mkdir()
    result_path = directory / "holdout_result.json"
    result_path.write_text(
        json.dumps(_payload(result), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    wrapper = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_regime_holdout_spent",
        "captured_at": captured_at.isoformat(),
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_fit.evidence_id,
        "result_path": str(result_path.resolve()),
        "result": _payload(result),
        "refit_after_holdout_allowed": False,
    }
    temporary = root / ".latest_holdout_result.json.tmp"
    temporary.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(pointer)
    return result, False


__all__ = [
    "DEFAULT_REGIME_HOLDOUT_POINTER",
    "DEFAULT_REGIME_VALIDATION_OUTPUT",
    "RegimeHoldoutResult",
    "spend_regime_holdout_once",
]
