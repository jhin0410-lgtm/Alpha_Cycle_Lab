"""Bind the validated V5 fit and score an explicit certified 2026Q3 bundle once.

This module never acquires 2026Q3 data. The readiness path only reproduces the already-seen
V5 development fit on its clean 21-row panel. Future holdout scoring requires an explicit
certified source bundle and then persists an immutable one-shot result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np

from alpha_cycle.intelligence.sk_hynix_company_gp_empirical_regime_fit import (
    CompanyGPEmpiricalRow,
    build_company_gp_empirical_fit,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout_protocol import (
    FrozenV5Q3HoldoutProtocol,
)
from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    FrozenCompanyGPEmpiricalMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)

DEFAULT_V5_Q3_HOLDOUT_BINDING = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v5_q3_holdout_validation_binding.json"
)
DEFAULT_V5_Q3_HOLDOUT_RESULT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v5_q3_holdout_result.json"
)


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
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {
        str(key): item
        for key, item in cast(dict[object, object], value).items()
    }


def _float(payload: dict[str, object], key: str) -> float:
    return float(str(payload.get(key, "nan")))


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class V5Q3ValidationBinding:
    evidence_id: str
    protocol_evidence_id: str
    method_evidence_id: str
    fit_evidence_id: str
    fit_evaluation_date: date
    training_periods: tuple[str, ...]
    coefficients: tuple[float, ...]
    training_mean_company_gross_margin: float
    training_snapshot_hash: str
    development_gate_passed: bool
    training_fit_reproduced_exactly: bool
    holdout_period: str = "2026Q3"
    holdout_loaded: bool = False
    holdout_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.protocol_evidence_id,
            self.method_evidence_id,
            self.fit_evidence_id,
            self.training_snapshot_hash,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("V5 Q3 validation binding hashes must be SHA-256")
        if self.fit_evaluation_date != date(2026, 8, 18):
            raise ValueError("V5 Q3 validation binding fit date drifted")
        if len(self.training_periods) != 21 or len(self.coefficients) != 7:
            raise ValueError("V5 Q3 validation binding dimensions drifted")
        if not 0.0 < self.training_mean_company_gross_margin < 1.0:
            raise ValueError(
                "V5 Q3 validation binding training mean gross margin is invalid"
            )
        if not self.development_gate_passed or not self.training_fit_reproduced_exactly:
            raise ValueError("V5 Q3 validation binding requires reproduced passed V5 fit")
        if (
            self.holdout_period != "2026Q3"
            or self.holdout_loaded
            or self.holdout_evaluated
        ):
            raise ValueError("V5 Q3 validation binding cannot expose holdout data")
        if any(
            (
                self.numeric_forward_forecast_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("V5 Q3 validation binding opened downstream outputs")


@dataclass(frozen=True)
class V5Q3CertifiedSourceBundle:
    evidence_id: str
    period_id: str
    source_evaluation_date: date
    company_profitability_evidence_id: str
    product_revenue_evidence_id: str
    cycle_driver_evidence_id: str
    company_revenue_krw_million: float
    product_total_revenue_krw_million: float
    actual_gross_profit_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp_direction_code: float
    dram_bit_volume_direction_code: float
    nand_asp_direction_code: float
    nand_bit_volume_direction_code: float
    company_profitability_certified: bool
    product_revenue_mix_certified: bool
    cycle_driver_directions_certified: bool
    source_bundle_certified_complete: bool

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.company_profitability_evidence_id,
            self.product_revenue_evidence_id,
            self.cycle_driver_evidence_id,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("V5 Q3 source bundle evidence ids must be SHA-256")
        if self.period_id != "2026Q3":
            raise ValueError("V5 Q3 source bundle period drifted")
        if (
            self.company_revenue_krw_million <= 0.0
            or self.product_total_revenue_krw_million <= 0.0
        ):
            raise ValueError("V5 Q3 source bundle revenue must be positive")
        if min(self.nand_revenue_krw_million, self.other_revenue_krw_million) < 0.0:
            raise ValueError("V5 Q3 source bundle product revenue cannot be negative")
        codes = (
            self.dram_asp_direction_code,
            self.dram_bit_volume_direction_code,
            self.nand_asp_direction_code,
            self.nand_bit_volume_direction_code,
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("V5 Q3 source bundle direction code is invalid")
        if not (
            self.company_profitability_certified
            and self.product_revenue_mix_certified
            and self.cycle_driver_directions_certified
            and self.source_bundle_certified_complete
        ):
            raise ValueError("V5 Q3 source bundle is not completely certified")

    @property
    def design_terms(self) -> tuple[float, ...]:
        revenue = self.company_revenue_krw_million
        return (
            revenue,
            revenue * self.dram_asp_direction_code,
            revenue * self.dram_bit_volume_direction_code,
            revenue * self.nand_asp_direction_code,
            revenue * self.nand_bit_volume_direction_code,
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
        )


@dataclass(frozen=True)
class V5Q3HoldoutResult:
    evidence_id: str
    protocol_evidence_id: str
    validation_binding_evidence_id: str
    method_evidence_id: str
    fit_evidence_id: str
    source_bundle_evidence_id: str
    holdout_period: str
    source_evaluation_date: date
    company_revenue_reconciled: bool
    company_revenue_krw_million: float
    actual_gross_profit_krw_million: float
    model_prediction_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float
    model_beats_benchmark: bool
    holdout_validation_passed: bool
    validation_scope: str = (
        "out_of_sample_contemporaneous_company_gp_relationship_only"
    )
    validates_pre_earnings_forecastability: bool = False
    holdout_spent: bool = True
    immutable_result: bool = True
    refit_after_holdout_allowed: bool = False
    product_margin_structural_interpretation_allowed: bool = False
    numeric_forward_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False
    investment_action_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.protocol_evidence_id,
            self.validation_binding_evidence_id,
            self.method_evidence_id,
            self.fit_evidence_id,
            self.source_bundle_evidence_id,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("V5 Q3 holdout result hashes must be SHA-256")
        if self.holdout_period != "2026Q3":
            raise ValueError("V5 Q3 holdout result period drifted")
        expected_better = (
            self.model_absolute_error_krw_million
            < self.benchmark_absolute_error_krw_million
        )
        if self.model_beats_benchmark != expected_better:
            raise ValueError("V5 Q3 holdout benchmark comparison is inconsistent")
        expected_pass = self.company_revenue_reconciled and expected_better
        if self.holdout_validation_passed != expected_pass:
            raise ValueError("V5 Q3 holdout validation flag is inconsistent")
        if self.validates_pre_earnings_forecastability:
            raise ValueError("V5 Q3 holdout cannot claim pre-earnings forecastability")
        if (
            not self.holdout_spent
            or not self.immutable_result
            or self.refit_after_holdout_allowed
        ):
            raise ValueError("V5 Q3 holdout immutability boundary drifted")
        if self.product_margin_structural_interpretation_allowed or any(
            (
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
                self.investment_action_enabled,
            )
        ):
            raise ValueError("V5 Q3 holdout opened prohibited downstream scope")


def build_v5_q3_validation_binding(
    protocol: FrozenV5Q3HoldoutProtocol,
    method: FrozenCompanyGPEmpiricalMethod,
    fit_report_path: str | Path,
    rows: tuple[CompanyGPEmpiricalRow, ...],
    contaminated_q1: CompanyGPEmpiricalRow,
) -> V5Q3ValidationBinding:
    root = _object(Path(fit_report_path), "V5 fit report")
    if root.get("status") != "skhynix_company_gp_empirical_v5_fit_completed":
        raise ValueError("V5 Q3 validation binding requires completed V5 fit report")
    if str(root.get("method_evidence_id", "")) != protocol.bound_method_evidence_id:
        raise ValueError("V5 Q3 validation binding fit-report method diverged")
    result_payload = _mapping(root.get("result"), "V5 fit result")
    if result_payload.get("development_gate_passed") is not True:
        raise ValueError("V5 Q3 validation binding requires passed V5 development gate")
    if (
        result_payload.get("future_holdout_loaded") is True
        or result_payload.get("future_holdout_evaluated") is True
    ):
        raise ValueError("V5 Q3 validation binding detected prior holdout exposure")
    fit_date = date.fromisoformat(str(result_payload.get("evaluation_date", "")))
    if fit_date != protocol.bound_fit_evaluation_date:
        raise ValueError("V5 Q3 validation binding fit evaluation date diverged")
    rebuilt = build_company_gp_empirical_fit(
        method,
        rows,
        contaminated_q1,
        evaluation_date=fit_date,
    )
    persisted_fit_evidence = str(result_payload.get("evidence_id", ""))
    if persisted_fit_evidence != rebuilt.evidence_id:
        raise ValueError("V5 Q3 validation binding could not reproduce persisted V5 fit")
    if rebuilt.method_evidence_id != protocol.bound_method_evidence_id:
        raise ValueError("V5 Q3 validation binding rebuilt method diverged")
    training_mean_margin = float(
        np.mean(
            [
                row.company_gross_profit_krw_million
                / row.company_revenue_krw_million
                for row in rows
            ]
        )
    )
    training_snapshot = tuple(
        (
            row.period_id,
            row.design_terms,
            row.company_gross_profit_krw_million,
        )
        for row in rows
    )
    training_hash = _sha(training_snapshot)
    stable: dict[str, object] = {
        "protocol_evidence_id": protocol.evidence_id,
        "method_evidence_id": method.evidence_id,
        "fit_evidence_id": rebuilt.evidence_id,
        "fit_evaluation_date": fit_date.isoformat(),
        "training_periods": rebuilt.training_periods,
        "coefficients": rebuilt.coefficients,
        "training_mean_company_gross_margin": training_mean_margin,
        "training_snapshot_hash": training_hash,
        "development_gate_passed": rebuilt.development_gate_passed,
        "training_fit_reproduced_exactly": True,
        "holdout_period": protocol.holdout_period,
        "holdout_loaded": False,
        "holdout_evaluated": False,
    }
    return V5Q3ValidationBinding(
        evidence_id=_sha(stable),
        protocol_evidence_id=protocol.evidence_id,
        method_evidence_id=method.evidence_id,
        fit_evidence_id=rebuilt.evidence_id,
        fit_evaluation_date=fit_date,
        training_periods=rebuilt.training_periods,
        coefficients=rebuilt.coefficients,
        training_mean_company_gross_margin=training_mean_margin,
        training_snapshot_hash=training_hash,
        development_gate_passed=rebuilt.development_gate_passed,
        training_fit_reproduced_exactly=True,
    )


def persist_v5_q3_validation_binding(
    binding: V5Q3ValidationBinding,
    path: str | Path = DEFAULT_V5_Q3_HOLDOUT_BINDING,
) -> Path:
    output = Path(path)
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_v5_q3_holdout_validation_binding_ready",
        "binding": asdict(binding),
    }
    _write(output, payload)
    return output


def load_v5_q3_validation_binding(
    path: str | Path = DEFAULT_V5_Q3_HOLDOUT_BINDING,
) -> V5Q3ValidationBinding:
    root = _object(Path(path), "V5 Q3 validation binding")
    if root.get("status") != "skhynix_v5_q3_holdout_validation_binding_ready":
        raise ValueError("V5 Q3 validation binding status is invalid")
    payload = _mapping(root.get("binding"), "V5 Q3 validation binding payload")
    periods = cast(list[object], payload.get("training_periods", []))
    coefficients = cast(list[object], payload.get("coefficients", []))
    return V5Q3ValidationBinding(
        evidence_id=str(payload.get("evidence_id", "")),
        protocol_evidence_id=str(payload.get("protocol_evidence_id", "")),
        method_evidence_id=str(payload.get("method_evidence_id", "")),
        fit_evidence_id=str(payload.get("fit_evidence_id", "")),
        fit_evaluation_date=date.fromisoformat(
            str(payload.get("fit_evaluation_date", ""))
        ),
        training_periods=tuple(str(item) for item in periods),
        coefficients=tuple(float(item) for item in coefficients),
        training_mean_company_gross_margin=_float(
            payload,
            "training_mean_company_gross_margin",
        ),
        training_snapshot_hash=str(payload.get("training_snapshot_hash", "")),
        development_gate_passed=payload.get("development_gate_passed") is True,
        training_fit_reproduced_exactly=(
            payload.get("training_fit_reproduced_exactly") is True
        ),
        holdout_period=str(payload.get("holdout_period", "")),
        holdout_loaded=payload.get("holdout_loaded") is True,
        holdout_evaluated=payload.get("holdout_evaluated") is True,
    )


def load_v5_q3_certified_source_bundle(
    path: str | Path,
) -> V5Q3CertifiedSourceBundle:
    root = _object(Path(path), "V5 Q3 certified source bundle")
    if (
        root.get("schema_version") != 1
        or root.get("status")
        != "skhynix_v5_q3_certified_source_bundle_complete"
    ):
        raise ValueError("V5 Q3 certified source bundle wrapper is invalid")
    payload = _mapping(root.get("bundle"), "V5 Q3 certified source bundle payload")
    unhashed = {key: value for key, value in payload.items() if key != "evidence_id"}
    if _sha(unhashed) != str(payload.get("evidence_id", "")):
        raise ValueError("V5 Q3 certified source bundle hash mismatch")
    return V5Q3CertifiedSourceBundle(
        evidence_id=str(payload.get("evidence_id", "")),
        period_id=str(payload.get("period_id", "")),
        source_evaluation_date=date.fromisoformat(
            str(payload.get("source_evaluation_date", ""))
        ),
        company_profitability_evidence_id=str(
            payload.get("company_profitability_evidence_id", "")
        ),
        product_revenue_evidence_id=str(
            payload.get("product_revenue_evidence_id", "")
        ),
        cycle_driver_evidence_id=str(payload.get("cycle_driver_evidence_id", "")),
        company_revenue_krw_million=_float(payload, "company_revenue_krw_million"),
        product_total_revenue_krw_million=_float(
            payload,
            "product_total_revenue_krw_million",
        ),
        actual_gross_profit_krw_million=_float(
            payload,
            "actual_gross_profit_krw_million",
        ),
        nand_revenue_krw_million=_float(payload, "nand_revenue_krw_million"),
        other_revenue_krw_million=_float(payload, "other_revenue_krw_million"),
        dram_asp_direction_code=_float(payload, "dram_asp_direction_code"),
        dram_bit_volume_direction_code=_float(
            payload,
            "dram_bit_volume_direction_code",
        ),
        nand_asp_direction_code=_float(payload, "nand_asp_direction_code"),
        nand_bit_volume_direction_code=_float(
            payload,
            "nand_bit_volume_direction_code",
        ),
        company_profitability_certified=(
            payload.get("company_profitability_certified") is True
        ),
        product_revenue_mix_certified=(
            payload.get("product_revenue_mix_certified") is True
        ),
        cycle_driver_directions_certified=(
            payload.get("cycle_driver_directions_certified") is True
        ),
        source_bundle_certified_complete=(
            payload.get("source_bundle_certified_complete") is True
        ),
    )


def _result_from_payload(payload: dict[str, object]) -> V5Q3HoldoutResult:
    return V5Q3HoldoutResult(
        evidence_id=str(payload.get("evidence_id", "")),
        protocol_evidence_id=str(payload.get("protocol_evidence_id", "")),
        validation_binding_evidence_id=str(
            payload.get("validation_binding_evidence_id", "")
        ),
        method_evidence_id=str(payload.get("method_evidence_id", "")),
        fit_evidence_id=str(payload.get("fit_evidence_id", "")),
        source_bundle_evidence_id=str(
            payload.get("source_bundle_evidence_id", "")
        ),
        holdout_period=str(payload.get("holdout_period", "")),
        source_evaluation_date=date.fromisoformat(
            str(payload.get("source_evaluation_date", ""))
        ),
        company_revenue_reconciled=(
            payload.get("company_revenue_reconciled") is True
        ),
        company_revenue_krw_million=_float(payload, "company_revenue_krw_million"),
        actual_gross_profit_krw_million=_float(
            payload,
            "actual_gross_profit_krw_million",
        ),
        model_prediction_krw_million=_float(payload, "model_prediction_krw_million"),
        model_absolute_error_krw_million=_float(
            payload,
            "model_absolute_error_krw_million",
        ),
        benchmark_prediction_krw_million=_float(
            payload,
            "benchmark_prediction_krw_million",
        ),
        benchmark_absolute_error_krw_million=_float(
            payload,
            "benchmark_absolute_error_krw_million",
        ),
        model_beats_benchmark=payload.get("model_beats_benchmark") is True,
        holdout_validation_passed=(
            payload.get("holdout_validation_passed") is True
        ),
        validation_scope=str(payload.get("validation_scope", "")),
        validates_pre_earnings_forecastability=(
            payload.get("validates_pre_earnings_forecastability") is True
        ),
        holdout_spent=payload.get("holdout_spent") is True,
        immutable_result=payload.get("immutable_result") is True,
        refit_after_holdout_allowed=(
            payload.get("refit_after_holdout_allowed") is True
        ),
        product_margin_structural_interpretation_allowed=(
            payload.get("product_margin_structural_interpretation_allowed") is True
        ),
        numeric_forward_forecast_enabled=(
            payload.get("numeric_forward_forecast_enabled") is True
        ),
        fair_value_estimate_enabled=(
            payload.get("fair_value_estimate_enabled") is True
        ),
        target_price_enabled=payload.get("target_price_enabled") is True,
        decision_score_enabled=payload.get("decision_score_enabled") is True,
        investment_action_enabled=payload.get("investment_action_enabled") is True,
    )


def _build_result(
    protocol: FrozenV5Q3HoldoutProtocol,
    binding: V5Q3ValidationBinding,
    source: V5Q3CertifiedSourceBundle,
) -> V5Q3HoldoutResult:
    delta_krw = int(
        round(
            (
                source.product_total_revenue_krw_million
                - source.company_revenue_krw_million
            )
            * 1_000_000.0
        )
    )
    reconciled = (
        abs(delta_krw) <= protocol.company_revenue_reconciliation_tolerance_krw
    )
    if not reconciled:
        raise ValueError("V5 Q3 holdout company/product revenue reconciliation failed")
    model_prediction = float(
        np.dot(
            np.asarray(source.design_terms, dtype=float),
            np.asarray(binding.coefficients, dtype=float),
        )
    )
    benchmark_prediction = (
        binding.training_mean_company_gross_margin
        * source.company_revenue_krw_million
    )
    model_error = abs(source.actual_gross_profit_krw_million - model_prediction)
    benchmark_error = abs(
        source.actual_gross_profit_krw_million - benchmark_prediction
    )
    better = model_error < benchmark_error
    common: dict[str, object] = {
        "protocol_evidence_id": protocol.evidence_id,
        "validation_binding_evidence_id": binding.evidence_id,
        "method_evidence_id": binding.method_evidence_id,
        "fit_evidence_id": binding.fit_evidence_id,
        "source_bundle_evidence_id": source.evidence_id,
        "holdout_period": source.period_id,
        "source_evaluation_date": source.source_evaluation_date.isoformat(),
        "company_revenue_reconciled": reconciled,
        "company_revenue_krw_million": source.company_revenue_krw_million,
        "actual_gross_profit_krw_million": source.actual_gross_profit_krw_million,
        "model_prediction_krw_million": model_prediction,
        "model_absolute_error_krw_million": model_error,
        "benchmark_prediction_krw_million": benchmark_prediction,
        "benchmark_absolute_error_krw_million": benchmark_error,
        "model_beats_benchmark": better,
        "holdout_validation_passed": better and reconciled,
        "validation_scope": (
            "out_of_sample_contemporaneous_company_gp_relationship_only"
        ),
        "validates_pre_earnings_forecastability": False,
        "holdout_spent": True,
        "immutable_result": True,
        "refit_after_holdout_allowed": False,
        "product_margin_structural_interpretation_allowed": False,
        "numeric_forward_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "investment_action_enabled": False,
    }
    return V5Q3HoldoutResult(
        evidence_id=_sha(common),
        protocol_evidence_id=protocol.evidence_id,
        validation_binding_evidence_id=binding.evidence_id,
        method_evidence_id=binding.method_evidence_id,
        fit_evidence_id=binding.fit_evidence_id,
        source_bundle_evidence_id=source.evidence_id,
        holdout_period=source.period_id,
        source_evaluation_date=source.source_evaluation_date,
        company_revenue_reconciled=reconciled,
        company_revenue_krw_million=source.company_revenue_krw_million,
        actual_gross_profit_krw_million=source.actual_gross_profit_krw_million,
        model_prediction_krw_million=model_prediction,
        model_absolute_error_krw_million=model_error,
        benchmark_prediction_krw_million=benchmark_prediction,
        benchmark_absolute_error_krw_million=benchmark_error,
        model_beats_benchmark=better,
        holdout_validation_passed=better and reconciled,
    )


def score_v5_q3_holdout_once(
    protocol: FrozenV5Q3HoldoutProtocol,
    binding: V5Q3ValidationBinding,
    source: V5Q3CertifiedSourceBundle,
    *,
    output: str | Path = DEFAULT_V5_Q3_HOLDOUT_RESULT,
) -> tuple[V5Q3HoldoutResult, bool]:
    if binding.protocol_evidence_id != protocol.evidence_id:
        raise ValueError("V5 Q3 scorer protocol/binding mismatch")
    if binding.method_evidence_id != protocol.bound_method_evidence_id:
        raise ValueError("V5 Q3 scorer method binding mismatch")
    if source.period_id != protocol.holdout_period:
        raise ValueError("V5 Q3 scorer source period mismatch")
    pointer = Path(output)
    if pointer.is_file():
        root = _object(pointer, "V5 Q3 immutable holdout result")
        if root.get("status") != "skhynix_v5_q3_holdout_spent":
            raise ValueError("V5 Q3 immutable holdout result status is invalid")
        payload = _mapping(root.get("result"), "V5 Q3 immutable result payload")
        unhashed = {
            key: value
            for key, value in payload.items()
            if key != "evidence_id"
        }
        if _sha(unhashed) != str(payload.get("evidence_id", "")):
            raise ValueError("V5 Q3 immutable holdout result hash mismatch")
        existing = _result_from_payload(payload)
        if existing.protocol_evidence_id != protocol.evidence_id:
            raise ValueError("V5 Q3 holdout was already spent under another protocol")
        if existing.validation_binding_evidence_id != binding.evidence_id:
            raise ValueError("V5 Q3 holdout was already spent under another V5 binding")
        if existing.source_bundle_evidence_id != source.evidence_id:
            raise ValueError("V5 Q3 holdout source bundle changed after first score")
        return existing, True

    result = _build_result(protocol, binding, source)
    wrapper: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_v5_q3_holdout_spent",
        "result": asdict(result),
    }
    _write(pointer, wrapper)
    return result, False


__all__ = [
    "DEFAULT_V5_Q3_HOLDOUT_BINDING",
    "DEFAULT_V5_Q3_HOLDOUT_RESULT",
    "V5Q3CertifiedSourceBundle",
    "V5Q3HoldoutResult",
    "V5Q3ValidationBinding",
    "build_v5_q3_validation_binding",
    "load_v5_q3_certified_source_bundle",
    "load_v5_q3_validation_binding",
    "persist_v5_q3_validation_binding",
    "score_v5_q3_holdout_once",
]
