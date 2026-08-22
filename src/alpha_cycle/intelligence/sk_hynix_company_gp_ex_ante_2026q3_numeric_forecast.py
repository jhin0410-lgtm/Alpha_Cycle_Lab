"""Lock the SK hynix 2026Q3 numeric company-GP forecast without reading the outcome."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature import (
    DEFAULT_2026Q3_FEATURE_VECTOR,
    FrozenProspectiveFeatureVector,
    load_prospective_feature_vector,
    load_selected_estimator_artifact,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    DEFAULT_SELECTED_ESTIMATOR_POINTER,
    FrozenSelectedEstimatorFullFit,
)

DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT = Path(
    "config/skhynix_company_gp_ex_ante_2026q3_numeric_forecast.v1.yaml"
)
DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-forecast"
)
DEFAULT_2026Q3_NUMERIC_FORECAST = (
    DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT / "latest_numeric_forecast.json"
)
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_STATUS = "skhynix_ex_ante_2026q3_numeric_forecast_locked_outcome_blind"
_EXPECTED_CANDIDATE = "lagged_gp_affine_ols"
_EXPECTED_PREDICTORS = ("lagged_company_gross_profit",)
_EXPECTED_BENCHMARK = "previous_reported_quarter_gross_profit_persistence"


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


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


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _aware_kst(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(_KOREA_TZ)


@dataclass(frozen=True)
class NumericForecastContract:
    evidence_id: str
    forecast_version: str
    status: str
    ticker: str
    target_metric: str
    target_period: str
    selected_estimator_path: str
    feature_vector_path: str
    selected_candidate_id: str
    predictors: tuple[str, ...]
    benchmark_id: str
    benchmark_prediction_rule: str
    numeric_prediction_interval_enabled: bool
    first_forecast_after_origin_without_locked_artifact_allowed: bool

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Numeric forecast contract evidence id must be SHA-256")
        if self.forecast_version != "1.0-locked-before-2026q3-origin":
            raise ValueError("Numeric forecast contract version drifted")
        if self.status != "frozen_before_2026q3_outcome":
            raise ValueError("Numeric forecast contract status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Numeric forecast ticker/target drifted")
        if self.target_period != "2026Q3":
            raise ValueError("Numeric forecast target period drifted")
        if self.selected_candidate_id != _EXPECTED_CANDIDATE:
            raise ValueError("Numeric forecast selected candidate drifted")
        if self.predictors != _EXPECTED_PREDICTORS:
            raise ValueError("Numeric forecast predictors drifted")
        if self.benchmark_id != _EXPECTED_BENCHMARK:
            raise ValueError("Numeric forecast benchmark drifted")
        if self.benchmark_prediction_rule != "lagged_company_gross_profit":
            raise ValueError("Numeric forecast benchmark rule drifted")
        if self.numeric_prediction_interval_enabled:
            raise ValueError("Numeric forecast cannot invent an unfrozen prediction interval")
        if self.first_forecast_after_origin_without_locked_artifact_allowed:
            raise ValueError("Numeric forecast cannot be first-created after origin")


def load_numeric_forecast_contract(
    path: str | Path = DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT,
) -> NumericForecastContract:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "Numeric forecast manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Numeric forecast manifest schema is invalid")
    body = _mapping(root.get("forecast"), "Numeric forecast body")
    if body.get("forecast_id") != "skhynix_company_gp_ex_ante_2026q3_numeric_forecast":
        raise ValueError("Numeric forecast id drifted")
    inputs = _mapping(body.get("locked_inputs"), "Numeric forecast locked inputs")
    prediction = _mapping(body.get("deterministic_prediction"), "Numeric forecast prediction")
    benchmark = _mapping(body.get("prospective_benchmark"), "Numeric forecast benchmark")
    uncertainty = _mapping(body.get("uncertainty_policy"), "Numeric forecast uncertainty")
    timing = _mapping(body.get("timing_policy"), "Numeric forecast timing")
    protected = _mapping(body.get("protected_boundary_after_forecast"), "Numeric protected")

    expected_prediction = {
        "estimator": "ordinary_least_squares",
        "use_frozen_raw_unit_intercept_and_coefficients": True,
        "verify_against_frozen_standardized_representation": True,
        "internal_rounding_allowed": False,
        "post_feature_model_refit_allowed": False,
        "post_feature_coefficient_change_allowed": False,
        "post_feature_predictor_change_allowed": False,
    }
    for key, expected in expected_prediction.items():
        if prediction.get(key) != expected:
            raise ValueError(f"Numeric forecast deterministic rule drifted: {key}")
    if benchmark.get("freeze_benchmark_prediction_now") is not True:
        raise ValueError("Numeric forecast benchmark was not frozen prospectively")
    if uncertainty.get("reason") != "no_pre_outcome_interval_calibration_rule_was_frozen":
        raise ValueError("Numeric forecast uncertainty rationale drifted")
    if uncertainty.get("historical_oos_mae_is_report_only_error_scale") is not True:
        raise ValueError("Numeric forecast historical OOS MAE role drifted")
    if timing.get("forecast_must_be_locked_not_after_forecast_origin") is not True:
        raise ValueError("Numeric forecast timing gate drifted")
    if timing.get("later_replay_of_existing_locked_artifact_allowed") is not True:
        raise ValueError("Numeric forecast replay policy drifted")

    expected_protected = {
        "prospective_feature_vector_frozen": True,
        "prospective_forecast_run": True,
        "2026q1_used_for_selection": False,
        "2026q3_target_read": False,
        "2026q3_source_outcome_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": True,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "investment_action_enabled": False,
    }
    for key, expected in expected_protected.items():
        if protected.get(key) != expected:
            raise ValueError(f"Numeric forecast protected boundary drifted: {key}")

    stable = {"schema_version": 1, "forecast": body}
    return NumericForecastContract(
        evidence_id=_sha(stable),
        forecast_version=str(body.get("forecast_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        target_period=str(body.get("target_period", "")),
        selected_estimator_path=str(inputs.get("selected_estimator_path", "")),
        feature_vector_path=str(inputs.get("prospective_feature_vector_path", "")),
        selected_candidate_id=str(prediction.get("selected_candidate_id", "")),
        predictors=tuple(
            str(item) for item in _array(prediction.get("predictors"), "predictors")
        ),
        benchmark_id=str(benchmark.get("benchmark_id", "")),
        benchmark_prediction_rule=str(benchmark.get("prediction_rule", "")),
        numeric_prediction_interval_enabled=(
            uncertainty.get("numeric_prediction_interval_enabled") is True
        ),
        first_forecast_after_origin_without_locked_artifact_allowed=(
            timing.get("first_forecast_after_origin_without_locked_artifact_allowed") is True
        ),
    )


@dataclass(frozen=True)
class LockedNumericForecast:
    evidence_id: str
    contract_evidence_id: str
    selected_estimator_evidence_id: str
    feature_vector_evidence_id: str
    protocol_evidence_id: str
    source_capture_evidence_id: str
    target_period: str
    forecast_origin: datetime
    forecast_locked_at: datetime
    selected_candidate_id: str
    predictors: tuple[str, ...]
    feature_values: tuple[float, ...]
    raw_unit_intercept: float
    raw_unit_coefficients: tuple[float, ...]
    standardized_input: tuple[float, ...]
    selected_forecast_krw_million: float
    benchmark_id: str
    benchmark_forecast_krw_million: float
    historical_selected_candidate_mae_krw_million: float
    historical_benchmark_mae_krw_million: float
    prediction_interval: None = None
    status: str = _STATUS
    prospective_feature_vector_frozen: bool = True
    prospective_forecast_run: bool = True
    q1_used_for_selection: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    q3_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = True

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.contract_evidence_id,
            self.selected_estimator_evidence_id,
            self.feature_vector_evidence_id,
            self.protocol_evidence_id,
            self.source_capture_evidence_id,
        ):
            if not _valid_sha(value):
                raise ValueError("Numeric forecast evidence ids must be SHA-256")
        if self.status != _STATUS or self.target_period != "2026Q3":
            raise ValueError("Numeric forecast status/period drifted")
        if self.selected_candidate_id != _EXPECTED_CANDIDATE:
            raise ValueError("Numeric forecast candidate drifted")
        if self.predictors != _EXPECTED_PREDICTORS or len(self.feature_values) != 1:
            raise ValueError("Numeric forecast predictor geometry drifted")
        if len(self.raw_unit_coefficients) != 1 or len(self.standardized_input) != 1:
            raise ValueError("Numeric forecast coefficient geometry drifted")
        numbers = (
            *self.feature_values,
            self.raw_unit_intercept,
            *self.raw_unit_coefficients,
            *self.standardized_input,
            self.selected_forecast_krw_million,
            self.benchmark_forecast_krw_million,
            self.historical_selected_candidate_mae_krw_million,
            self.historical_benchmark_mae_krw_million,
        )
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("Numeric forecast contains non-finite values")
        if _aware_kst(self.forecast_locked_at, "forecast_locked_at") > _aware_kst(
            self.forecast_origin, "forecast_origin"
        ):
            raise ValueError("Numeric forecast was first locked after forecast origin")
        if self.prediction_interval is not None:
            raise ValueError("Numeric forecast invented an unfrozen prediction interval")
        if not self.prospective_feature_vector_frozen or not self.prospective_forecast_run:
            raise ValueError("Numeric forecast execution flags drifted")
        if any(
            (
                self.q1_used_for_selection,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.q3_evaluated,
            )
        ):
            raise ValueError("Numeric forecast opened protected outcome state")
        if not self.numeric_forward_forecast_enabled:
            raise ValueError("Numeric forecast did not record numeric forecast enablement")


def _forecast_payload(item: LockedNumericForecast) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "selected_estimator_evidence_id": item.selected_estimator_evidence_id,
        "feature_vector_evidence_id": item.feature_vector_evidence_id,
        "protocol_evidence_id": item.protocol_evidence_id,
        "source_capture_evidence_id": item.source_capture_evidence_id,
        "target_period": item.target_period,
        "forecast_origin": item.forecast_origin.isoformat(),
        "forecast_locked_at": item.forecast_locked_at.isoformat(),
        "selected_candidate_id": item.selected_candidate_id,
        "predictors": list(item.predictors),
        "feature_values": list(item.feature_values),
        "raw_unit_intercept": item.raw_unit_intercept,
        "raw_unit_coefficients": list(item.raw_unit_coefficients),
        "standardized_input": list(item.standardized_input),
        "selected_forecast_krw_million": item.selected_forecast_krw_million,
        "benchmark_id": item.benchmark_id,
        "benchmark_forecast_krw_million": item.benchmark_forecast_krw_million,
        "historical_selected_candidate_mae_krw_million": (
            item.historical_selected_candidate_mae_krw_million
        ),
        "historical_benchmark_mae_krw_million": item.historical_benchmark_mae_krw_million,
        "prediction_interval": item.prediction_interval,
        "status": item.status,
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "q1_used_for_selection": item.q1_used_for_selection,
        "q3_target_read": item.q3_target_read,
        "q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
    }


def build_locked_numeric_forecast(
    contract: NumericForecastContract,
    selected: FrozenSelectedEstimatorFullFit,
    feature: FrozenProspectiveFeatureVector,
    *,
    forecast_locked_at: datetime,
) -> LockedNumericForecast:
    if feature.target_period != contract.target_period:
        raise ValueError("Numeric forecast feature target period drifted")
    if feature.selected_estimator_evidence_id != selected.evidence_id:
        raise ValueError("Numeric forecast feature/estimator binding drifted")
    if selected.selected_candidate_id != contract.selected_candidate_id:
        raise ValueError("Numeric forecast selected candidate binding drifted")
    if selected.predictors != contract.predictors or feature.predictors != contract.predictors:
        raise ValueError("Numeric forecast predictor binding drifted")
    if any(
        (
            feature.prospective_forecast_run,
            feature.q3_target_read,
            feature.q3_source_outcome_loaded,
            feature.q3_evaluated,
            feature.numeric_forward_forecast_enabled,
        )
    ):
        raise ValueError("Numeric forecast input feature artifact opened future state")
    if selected.prospective_forecast_run or selected.q3_target_read or selected.q3_evaluated:
        raise ValueError("Numeric forecast selected estimator artifact opened future state")

    locked_at = _aware_kst(forecast_locked_at, "forecast_locked_at")
    origin = _aware_kst(feature.forecast_origin, "forecast_origin")
    if locked_at > origin:
        raise ValueError("2026Q3 numeric forecast origin was missed before first forecast lock")
    if locked_at < _aware_kst(feature.frozen_at, "feature frozen_at"):
        raise ValueError("Numeric forecast cannot predate the prospective feature freeze")

    raw_prediction = selected.raw_unit_intercept + sum(
        coefficient * value
        for coefficient, value in zip(
            selected.raw_unit_coefficients,
            feature.feature_values,
            strict=True,
        )
    )
    standardized_input = tuple(
        (value - mean) / scale
        for value, mean, scale in zip(
            feature.feature_values,
            selected.predictor_means,
            selected.predictor_scales,
            strict=True,
        )
    )
    standardized_prediction = selected.standardized_coefficients[0] + sum(
        coefficient * value
        for coefficient, value in zip(
            selected.standardized_coefficients[1:], standardized_input, strict=True
        )
    )
    if not math.isclose(raw_prediction, standardized_prediction, rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("Numeric forecast raw/standardized representations disagree")

    benchmark_prediction = feature.feature_values[0]
    provisional = LockedNumericForecast(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        selected_estimator_evidence_id=selected.evidence_id,
        feature_vector_evidence_id=feature.evidence_id,
        protocol_evidence_id=feature.protocol_evidence_id,
        source_capture_evidence_id=feature.source_capture_evidence_id,
        target_period=feature.target_period,
        forecast_origin=origin,
        forecast_locked_at=locked_at,
        selected_candidate_id=selected.selected_candidate_id,
        predictors=selected.predictors,
        feature_values=feature.feature_values,
        raw_unit_intercept=selected.raw_unit_intercept,
        raw_unit_coefficients=selected.raw_unit_coefficients,
        standardized_input=standardized_input,
        selected_forecast_krw_million=float(raw_prediction),
        benchmark_id=contract.benchmark_id,
        benchmark_forecast_krw_million=float(benchmark_prediction),
        historical_selected_candidate_mae_krw_million=(
            selected.historical_selected_candidate_mae_krw_million
        ),
        historical_benchmark_mae_krw_million=selected.historical_benchmark_mae_krw_million,
    )
    return replace(provisional, evidence_id=_sha(_forecast_payload(provisional)))


def persist_locked_numeric_forecast(
    item: LockedNumericForecast,
    *,
    output: str | Path = DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT,
) -> Path:
    if _sha(_forecast_payload(item)) != item.evidence_id:
        raise ValueError("Numeric forecast evidence hash drifted before persistence")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _STATUS,
        "forecast": {"evidence_id": item.evidence_id, **_forecast_payload(item)},
    }
    encoded = _canonical_bytes(payload)
    immutable = root / f"numeric-forecast-{item.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("Numeric forecast immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_numeric_forecast.json"
    if pointer.exists() and pointer.read_bytes() != encoded:
        raise ValueError("Numeric forecast is already locked to different evidence")
    temporary = root / ".latest_numeric_forecast.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def load_locked_numeric_forecast(
    path: str | Path = DEFAULT_2026Q3_NUMERIC_FORECAST,
) -> LockedNumericForecast:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Numeric forecast artifact")
    if root.get("schema_version") != 1 or root.get("status") != _STATUS:
        raise ValueError("Numeric forecast artifact status is invalid")
    body = _mapping(root.get("forecast"), "Numeric forecast artifact body")
    item = LockedNumericForecast(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        selected_estimator_evidence_id=str(body.get("selected_estimator_evidence_id", "")),
        feature_vector_evidence_id=str(body.get("feature_vector_evidence_id", "")),
        protocol_evidence_id=str(body.get("protocol_evidence_id", "")),
        source_capture_evidence_id=str(body.get("source_capture_evidence_id", "")),
        target_period=str(body.get("target_period", "")),
        forecast_origin=datetime.fromisoformat(str(body.get("forecast_origin", ""))),
        forecast_locked_at=datetime.fromisoformat(str(body.get("forecast_locked_at", ""))),
        selected_candidate_id=str(body.get("selected_candidate_id", "")),
        predictors=tuple(str(value) for value in _array(body.get("predictors"), "predictors")),
        feature_values=tuple(
            float(str(value)) for value in _array(body.get("feature_values"), "feature_values")
        ),
        raw_unit_intercept=float(str(body.get("raw_unit_intercept", "nan"))),
        raw_unit_coefficients=tuple(
            float(str(value))
            for value in _array(body.get("raw_unit_coefficients"), "raw_unit_coefficients")
        ),
        standardized_input=tuple(
            float(str(value))
            for value in _array(body.get("standardized_input"), "standardized_input")
        ),
        selected_forecast_krw_million=float(
            str(body.get("selected_forecast_krw_million", "nan"))
        ),
        benchmark_id=str(body.get("benchmark_id", "")),
        benchmark_forecast_krw_million=float(
            str(body.get("benchmark_forecast_krw_million", "nan"))
        ),
        historical_selected_candidate_mae_krw_million=float(
            str(body.get("historical_selected_candidate_mae_krw_million", "nan"))
        ),
        historical_benchmark_mae_krw_million=float(
            str(body.get("historical_benchmark_mae_krw_million", "nan"))
        ),
        prediction_interval=None,
        status=str(body.get("status", "")),
        prospective_feature_vector_frozen=(body.get("prospective_feature_vector_frozen") is True),
        prospective_forecast_run=body.get("prospective_forecast_run") is True,
        q1_used_for_selection=body.get("q1_used_for_selection") is True,
        q3_target_read=body.get("q3_target_read") is True,
        q3_source_outcome_loaded=body.get("q3_source_outcome_loaded") is True,
        q3_evaluated=body.get("q3_evaluated") is True,
        numeric_forward_forecast_enabled=(body.get("numeric_forward_forecast_enabled") is True),
    )
    if _sha(_forecast_payload(item)) != item.evidence_id:
        raise ValueError("Numeric forecast artifact evidence hash mismatch")
    return item


def lock_2026q3_numeric_forecast(
    *,
    forecast_locked_at: datetime | None = None,
    contract_path: str | Path = DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT,
    output: str | Path = DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT,
) -> tuple[LockedNumericForecast, Path, bool]:
    contract = load_numeric_forecast_contract(contract_path)
    selected = load_selected_estimator_artifact(contract.selected_estimator_path)
    feature = load_prospective_feature_vector(contract.feature_vector_path)
    pointer = Path(output) / "latest_numeric_forecast.json"
    if pointer.is_file():
        item = load_locked_numeric_forecast(pointer)
        if item.contract_evidence_id != contract.evidence_id:
            raise ValueError("Locked numeric forecast belongs to another contract")
        if item.selected_estimator_evidence_id != selected.evidence_id:
            raise ValueError("Locked numeric forecast selected estimator drifted")
        if item.feature_vector_evidence_id != feature.evidence_id:
            raise ValueError("Locked numeric forecast feature vector drifted")
        return item, pointer, True

    now = _aware_kst(
        forecast_locked_at if forecast_locked_at is not None else datetime.now(_KOREA_TZ),
        "forecast_locked_at",
    )
    item = build_locked_numeric_forecast(contract, selected, feature, forecast_locked_at=now)
    persisted = persist_locked_numeric_forecast(item, output=output)
    return item, persisted, False


__all__ = [
    "DEFAULT_2026Q3_NUMERIC_FORECAST",
    "DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT",
    "DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT",
    "LockedNumericForecast",
    "NumericForecastContract",
    "build_locked_numeric_forecast",
    "load_locked_numeric_forecast",
    "load_numeric_forecast_contract",
    "lock_2026q3_numeric_forecast",
    "persist_locked_numeric_forecast",
]
