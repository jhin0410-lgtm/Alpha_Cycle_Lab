"""Freeze the 2026Q3 SK hynix prospective feature vector before forecast origin.

This stage inherits the already selected full-20 estimator and the already validated
OpenDART accounting semantics. It may capture only the 2026Q2 lagged company filing needed
by the selected predictor. The 2026Q3 realized outcome is never requested or inspected.

The first live source response is persisted before feature extraction. Any later replay uses
those exact captured bytes, so parser repair or reruns cannot refresh the prospective input.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation_v2 import (
    load_frozen_historical_schema_repair_v2,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    load_frozen_company_gp_ex_ante_protocol,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    FrozenSelectedEstimatorFullFit,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT = Path(
    "config/skhynix_company_gp_ex_ante_2026q3_prospective_feature_freeze.v1.yaml"
)
DEFAULT_2026Q3_PROSPECTIVE_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-prospective"
)
DEFAULT_2026Q3_SOURCE_CAPTURE = (
    DEFAULT_2026Q3_PROSPECTIVE_OUTPUT / "latest_source_capture.json"
)
DEFAULT_2026Q3_FEATURE_VECTOR = (
    DEFAULT_2026Q3_PROSPECTIVE_OUTPUT / "latest_feature_vector.json"
)
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_CAPTURE_STATUS = "skhynix_ex_ante_2026q3_lagged_source_payload_locked_pre_extraction"
_VECTOR_STATUS = "skhynix_ex_ante_2026q3_prospective_feature_vector_frozen"
_SELECTED_ESTIMATOR_STATUS = "skhynix_ex_ante_selected_estimator_full_twenty_row_fit_frozen"
_EXPECTED_TARGET_PERIOD = "2026Q3"
_EXPECTED_SOURCE_PERIOD = "2026Q2"
_EXPECTED_PREDICTORS = ("lagged_company_gross_profit",)
_EXPECTED_CANDIDATE = "lagged_gp_affine_ols"
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


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


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"Prospective source {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Prospective source {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Prospective source {label} must be integral KRW")
    return int(amount)


def _receipt_date(receipt: str) -> date:
    if len(receipt) != 14 or not receipt.isdigit():
        raise ValueError("Prospective source receipt number must be fourteen digits")
    return date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))


def _source_available_at(receipt: str) -> datetime:
    return datetime.combine(_receipt_date(receipt), time(23, 59, 59), tzinfo=_KOREA_TZ)


def _aware_kst(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(_KOREA_TZ)


@dataclass(frozen=True)
class ProspectiveFeatureFreezeContract:
    evidence_id: str
    freeze_version: str
    status: str
    ticker: str
    target_metric: str
    target_period: str
    source_period: str
    protocol_path: str
    selected_estimator_path: str
    historical_execution_v2_path: str
    required_selected_candidate_id: str
    required_predictors: tuple[str, ...]
    business_year: int
    report_code: str
    fs_div: str
    amount_field: str
    raw_capture_before_extraction: bool
    source_refresh_allowed: bool
    first_capture_not_after_origin: bool
    early_lock_is_final: bool

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Prospective feature contract evidence id must be SHA-256")
        if self.freeze_version != "1.0-frozen-before-2026q3-origin":
            raise ValueError("Prospective feature contract version drifted")
        if self.status != "frozen_before_2026q3_forecast_origin":
            raise ValueError("Prospective feature contract status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Prospective feature contract ticker/target drifted")
        if self.target_period != _EXPECTED_TARGET_PERIOD or self.source_period != _EXPECTED_SOURCE_PERIOD:
            raise ValueError("Prospective feature period mapping drifted")
        if self.required_selected_candidate_id != _EXPECTED_CANDIDATE:
            raise ValueError("Prospective feature selected candidate drifted")
        if self.required_predictors != _EXPECTED_PREDICTORS:
            raise ValueError("Prospective feature predictor set drifted")
        if self.business_year != 2026 or self.report_code != "11012" or self.fs_div != "CFS":
            raise ValueError("Prospective feature filing geometry drifted")
        if self.amount_field != "thstrm_amount":
            raise ValueError("Prospective feature amount field drifted")
        if not self.raw_capture_before_extraction or not self.first_capture_not_after_origin:
            raise ValueError("Prospective feature capture gate drifted")
        if self.source_refresh_allowed or not self.early_lock_is_final:
            raise ValueError("Prospective feature contract opened source refresh")


def load_prospective_feature_freeze_contract(
    path: str | Path = DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT,
) -> ProspectiveFeatureFreezeContract:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "Prospective feature freeze manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Prospective feature freeze schema is invalid")
    body = _mapping(root.get("freeze"), "Prospective feature freeze body")
    if body.get("freeze_id") != "skhynix_company_gp_ex_ante_2026q3_prospective_feature_vector":
        raise ValueError("Prospective feature freeze id drifted")
    inputs = _mapping(body.get("locked_inputs"), "Prospective feature locked inputs")
    inheritance = _mapping(
        body.get("selected_predictor_inheritance"),
        "Prospective feature predictor inheritance",
    )
    source = _mapping(body.get("source_policy"), "Prospective feature source policy")
    timing = _mapping(body.get("timing_policy"), "Prospective feature timing policy")
    protected = _mapping(body.get("protected_boundary"), "Prospective feature protected boundary")

    if inheritance.get("predictor_definition") != (
        "previous_reported_quarter_company_gross_profit_krw_million"
    ):
        raise ValueError("Prospective feature predictor definition drifted")
    if inheritance.get("source_period_rule") != "immediately_preceding_calendar_quarter":
        raise ValueError("Prospective feature source-period rule drifted")
    for key in ("predictor_change_allowed", "feature_addition_allowed", "feature_substitution_allowed"):
        if inheritance.get(key) is not False:
            raise ValueError("Prospective feature contract reopened selected predictor scope")

    expected_source = {
        "provider": "opendart",
        "endpoint": "fnlttSinglAcntAll",
        "account_alias_policy_source": "historical_execution_v2",
        "allowed_statement_divisions_source": "historical_execution_v2",
        "require_revenue_minus_cost_equals_gross_profit": True,
        "require_same_receipt_for_selected_accounts": True,
        "require_source_available_not_after_forecast_origin": True,
        "require_source_available_not_after_raw_capture_time": True,
        "raw_payload_capture_before_feature_extraction": True,
        "raw_payload_refresh_after_first_capture_allowed": False,
        "account_name_fuzzy_matching_allowed": False,
        "arithmetic_target_reconstruction_allowed": False,
        "source_fallback_allowed": False,
        "correction_search_or_selection_allowed": False,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise ValueError(f"Prospective feature source policy drifted: {key}")

    expected_timing = {
        "forecast_origin_source": "frozen_forecast_protocol",
        "first_live_capture_must_occur_not_after_forecast_origin": True,
        "early_lock_is_final_for_2026q3": True,
        "information_arriving_after_first_live_capture_allowed": False,
        "fallback_period_if_origin_missed_without_capture": "2026Q4",
    }
    for key, expected in expected_timing.items():
        if timing.get(key) != expected:
            raise ValueError(f"Prospective feature timing policy drifted: {key}")

    protected_false = (
        "prospective_feature_vector_frozen_before_run",
        "prospective_forecast_run",
        "2026q1_used_for_selection",
        "2026q3_target_read",
        "2026q3_source_outcome_loaded",
        "2026q3_evaluated",
        "numeric_forward_forecast_enabled",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
        "investment_action_enabled",
    )
    if any(protected.get(key) is not False for key in protected_false):
        raise ValueError("Prospective feature contract opened protected future state")

    stable = {"schema_version": 1, "freeze": body}
    return ProspectiveFeatureFreezeContract(
        evidence_id=_sha(stable),
        freeze_version=str(body.get("freeze_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        target_period=str(body.get("target_period", "")),
        source_period=str(body.get("source_period", "")),
        protocol_path=str(inputs.get("forecast_protocol_path", "")),
        selected_estimator_path=str(inputs.get("selected_estimator_path", "")),
        historical_execution_v2_path=str(inputs.get("historical_execution_v2_path", "")),
        required_selected_candidate_id=str(inheritance.get("required_selected_candidate_id", "")),
        required_predictors=tuple(
            str(item)
            for item in _array(inheritance.get("required_predictors"), "required_predictors")
        ),
        business_year=int(str(source.get("business_year", -1))),
        report_code=str(source.get("report_code", "")),
        fs_div=str(source.get("fs_div", "")),
        amount_field=str(source.get("current_term_amount_field", "")),
        raw_capture_before_extraction=(
            source.get("raw_payload_capture_before_feature_extraction") is True
        ),
        source_refresh_allowed=(
            source.get("raw_payload_refresh_after_first_capture_allowed") is True
        ),
        first_capture_not_after_origin=(
            timing.get("first_live_capture_must_occur_not_after_forecast_origin") is True
        ),
        early_lock_is_final=timing.get("early_lock_is_final_for_2026q3") is True,
    )


@dataclass(frozen=True)
class ProspectiveSourceCapture:
    evidence_id: str
    contract_evidence_id: str
    historical_execution_evidence_id: str
    target_period: str
    source_period: str
    forecast_origin: datetime
    captured_at: datetime
    raw_payload_sha256: str
    captured_payload_bytes_sha256: str
    status: str = _CAPTURE_STATUS

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.contract_evidence_id,
            self.historical_execution_evidence_id,
            self.raw_payload_sha256,
            self.captured_payload_bytes_sha256,
        ):
            if not _valid_sha(value):
                raise ValueError("Prospective source capture evidence/hash must be SHA-256")
        if self.target_period != _EXPECTED_TARGET_PERIOD or self.source_period != _EXPECTED_SOURCE_PERIOD:
            raise ValueError("Prospective source capture period mapping drifted")
        if self.status != _CAPTURE_STATUS:
            raise ValueError("Prospective source capture status drifted")
        origin = _aware_kst(self.forecast_origin, "Prospective source forecast origin")
        captured = _aware_kst(self.captured_at, "Prospective source captured_at")
        if captured > origin:
            raise ValueError("Prospective source was first captured after forecast origin")


def _source_capture_payload(item: ProspectiveSourceCapture) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "historical_execution_evidence_id": item.historical_execution_evidence_id,
        "target_period": item.target_period,
        "source_period": item.source_period,
        "forecast_origin": item.forecast_origin.isoformat(),
        "captured_at": item.captured_at.isoformat(),
        "raw_payload_sha256": item.raw_payload_sha256,
        "captured_payload_bytes_sha256": item.captured_payload_bytes_sha256,
        "status": item.status,
    }


def build_prospective_source_capture(
    contract: ProspectiveFeatureFreezeContract,
    *,
    historical_execution_evidence_id: str,
    forecast_origin: datetime,
    captured_at: datetime,
    raw_payload: object,
) -> ProspectiveSourceCapture:
    canonical = _canonical_bytes(raw_payload)
    provisional = ProspectiveSourceCapture(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        historical_execution_evidence_id=historical_execution_evidence_id,
        target_period=contract.target_period,
        source_period=contract.source_period,
        forecast_origin=_aware_kst(forecast_origin, "Prospective source forecast origin"),
        captured_at=_aware_kst(captured_at, "Prospective source captured_at"),
        raw_payload_sha256=_sha(raw_payload),
        captured_payload_bytes_sha256=_sha_bytes(canonical),
    )
    return replace(provisional, evidence_id=_sha(_source_capture_payload(provisional)))


def persist_prospective_source_capture(
    capture: ProspectiveSourceCapture,
    raw_payload: object,
    *,
    output: str | Path = DEFAULT_2026Q3_PROSPECTIVE_OUTPUT,
) -> Path:
    if _sha(_source_capture_payload(capture)) != capture.evidence_id:
        raise ValueError("Prospective source capture evidence hash drifted")
    canonical = _canonical_bytes(raw_payload)
    if _sha(raw_payload) != capture.raw_payload_sha256:
        raise ValueError("Prospective source capture payload hash drifted")
    if _sha_bytes(canonical) != capture.captured_payload_bytes_sha256:
        raise ValueError("Prospective source capture byte hash drifted")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    pointer = root / "latest_source_capture.json"
    if pointer.exists():
        existing, _raw = load_prospective_source_capture(pointer)
        if existing.evidence_id != capture.evidence_id:
            raise ValueError("Prospective source capture is already locked and cannot refresh")
        return pointer

    artifact = root / f"source-capture-{capture.evidence_id}"
    temporary = root / f".{artifact.name}.tmp"
    if artifact.exists() or temporary.exists():
        raise ValueError("Prospective source capture artifact path already exists")
    temporary.mkdir()
    try:
        raw_root = temporary / "raw"
        raw_root.mkdir()
        (raw_root / "2026Q2.json").write_bytes(canonical)
        payload = {
            "schema_version": 1,
            "status": _CAPTURE_STATUS,
            "capture": {"evidence_id": capture.evidence_id, **_source_capture_payload(capture)},
        }
        (temporary / "capture.json").write_bytes(_canonical_bytes(payload))
        temporary.rename(artifact)
        pointer_payload = {**payload, "artifact_directory": str(artifact.resolve())}
        pointer_tmp = root / ".latest_source_capture.json.tmp"
        pointer_tmp.write_bytes(_canonical_bytes(pointer_payload))
        pointer_tmp.replace(pointer)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    replayed, _raw = load_prospective_source_capture(pointer)
    if replayed.evidence_id != capture.evidence_id:
        raise ValueError("Prospective source capture persistence replay failed")
    return pointer


def load_prospective_source_capture(
    path: str | Path = DEFAULT_2026Q3_SOURCE_CAPTURE,
) -> tuple[ProspectiveSourceCapture, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Prospective source capture artifact")
    if root.get("schema_version") != 1 or root.get("status") != _CAPTURE_STATUS:
        raise ValueError("Prospective source capture artifact status is invalid")
    body = _mapping(root.get("capture"), "Prospective source capture body")
    capture = ProspectiveSourceCapture(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        historical_execution_evidence_id=str(
            body.get("historical_execution_evidence_id", "")
        ),
        target_period=str(body.get("target_period", "")),
        source_period=str(body.get("source_period", "")),
        forecast_origin=datetime.fromisoformat(str(body.get("forecast_origin", ""))),
        captured_at=datetime.fromisoformat(str(body.get("captured_at", ""))),
        raw_payload_sha256=str(body.get("raw_payload_sha256", "")),
        captured_payload_bytes_sha256=str(body.get("captured_payload_bytes_sha256", "")),
        status=str(body.get("status", "")),
    )
    if _sha(_source_capture_payload(capture)) != capture.evidence_id:
        raise ValueError("Prospective source capture evidence hash mismatch")
    artifact_directory = str(root.get("artifact_directory", ""))
    if not artifact_directory:
        raise ValueError("Prospective source capture artifact directory is missing")
    raw_path = Path(artifact_directory) / "raw" / "2026Q2.json"
    if not raw_path.is_file():
        raise ValueError("Prospective source capture raw payload is missing")
    raw_bytes = raw_path.read_bytes()
    if _sha_bytes(raw_bytes) != capture.captured_payload_bytes_sha256:
        raise ValueError("Prospective source capture raw byte hash mismatch")
    raw_payload: object = json.loads(raw_bytes.decode("utf-8"))
    if _sha(raw_payload) != capture.raw_payload_sha256:
        raise ValueError("Prospective source capture raw payload hash mismatch")
    return capture, raw_payload


def _selected_estimator_payload(item: FrozenSelectedEstimatorFullFit) -> dict[str, object]:
    payload = asdict(item)
    payload["training_periods"] = list(item.training_periods)
    payload["predictors"] = list(item.predictors)
    payload["predictor_means"] = list(item.predictor_means)
    payload["predictor_scales"] = list(item.predictor_scales)
    payload["standardized_coefficients"] = list(item.standardized_coefficients)
    payload["raw_unit_coefficients"] = list(item.raw_unit_coefficients)
    payload.pop("evidence_id")
    return payload


def load_selected_estimator_artifact(path: str | Path) -> FrozenSelectedEstimatorFullFit:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Selected estimator artifact")
    if root.get("schema_version") != 1 or root.get("status") != _SELECTED_ESTIMATOR_STATUS:
        raise ValueError("Selected estimator artifact status is invalid")
    body = _mapping(root.get("selected_estimator"), "Selected estimator body")
    item = FrozenSelectedEstimatorFullFit(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        execution_evidence_id=str(body.get("execution_evidence_id", "")),
        scope_evidence_id=str(body.get("scope_evidence_id", "")),
        combined_bundle_evidence_id=str(body.get("combined_bundle_evidence_id", "")),
        target_join_evidence_id=str(body.get("target_join_evidence_id", "")),
        target_source_evidence_id=str(body.get("target_source_evidence_id", "")),
        raw_target_capture_evidence_id=str(body.get("raw_target_capture_evidence_id", "")),
        backtest_evidence_id=str(body.get("backtest_evidence_id", "")),
        estimator_freeze_evidence_id=str(body.get("estimator_freeze_evidence_id", "")),
        selected_candidate_id=str(body.get("selected_candidate_id", "")),
        estimator=str(body.get("estimator", "")),
        parameter_count=int(str(body.get("parameter_count", -1))),
        predictors=tuple(str(value) for value in _array(body.get("predictors"), "predictors")),
        training_periods=tuple(
            str(value) for value in _array(body.get("training_periods"), "training_periods")
        ),
        training_row_count=int(str(body.get("training_row_count", -1))),
        scaling_ddof=int(str(body.get("scaling_ddof", -1))),
        predictor_means=tuple(
            float(str(value)) for value in _array(body.get("predictor_means"), "predictor_means")
        ),
        predictor_scales=tuple(
            float(str(value)) for value in _array(body.get("predictor_scales"), "predictor_scales")
        ),
        standardized_coefficients=tuple(
            float(str(value))
            for value in _array(body.get("standardized_coefficients"), "standardized_coefficients")
        ),
        raw_unit_intercept=float(str(body.get("raw_unit_intercept", "nan"))),
        raw_unit_coefficients=tuple(
            float(str(value))
            for value in _array(body.get("raw_unit_coefficients"), "raw_unit_coefficients")
        ),
        design_rank=int(str(body.get("design_rank", -1))),
        residual_degrees_of_freedom=int(str(body.get("residual_degrees_of_freedom", -1))),
        condition_number=float(str(body.get("condition_number", "nan"))),
        training_mae_krw_million=float(str(body.get("training_mae_krw_million", "nan"))),
        training_rmse_krw_million=float(str(body.get("training_rmse_krw_million", "nan"))),
        historical_benchmark_mae_krw_million=float(
            str(body.get("historical_benchmark_mae_krw_million", "nan"))
        ),
        historical_selected_candidate_mae_krw_million=float(
            str(body.get("historical_selected_candidate_mae_krw_million", "nan"))
        ),
        historical_relative_mae_improvement=float(
            str(body.get("historical_relative_mae_improvement", "nan"))
        ),
        status=str(body.get("status", "")),
        prospective_feature_vector_frozen=(body.get("prospective_feature_vector_frozen") is True),
        prospective_forecast_run=body.get("prospective_forecast_run") is True,
        q1_used_for_selection=body.get("q1_used_for_selection") is True,
        q3_target_read=body.get("q3_target_read") is True,
        q3_source_outcome_loaded=body.get("q3_source_outcome_loaded") is True,
        q3_evaluated=body.get("q3_evaluated") is True,
        numeric_forward_forecast_enabled=(body.get("numeric_forward_forecast_enabled") is True),
    )
    if _sha(_selected_estimator_payload(item)) != item.evidence_id:
        raise ValueError("Selected estimator artifact evidence hash mismatch")
    return item


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    root = _mapping(raw_payload, "Prospective OpenDART raw payload")
    financials = _mapping(root.get("financials"), "Prospective OpenDART financials")
    rows_raw = _array(financials.get("list"), "Prospective OpenDART financial list")
    rows = tuple(_mapping(item, "Prospective OpenDART financial row") for item in rows_raw)
    if not rows:
        raise ValueError("Prospective OpenDART financial list is empty")
    return rows


def _select_account(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    *,
    business_year: int,
    report_code: str,
    amount_field: str,
    label: str,
) -> tuple[int, str]:
    accepted = {item.casefold() for item in account_ids}
    matches: list[tuple[int, str]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(business_year):
            continue
        if row_code and row_code != report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        _receipt_date(receipt)
        matches.append((_integral_krw(row.get(amount_field), label), receipt))
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"Prospective source account must resolve uniquely: {business_year} "
            f"report_code={report_code} label={label} count={len(unique)}"
        )
    return unique[0]


@dataclass(frozen=True)
class FrozenProspectiveFeatureVector:
    evidence_id: str
    contract_evidence_id: str
    protocol_evidence_id: str
    selected_estimator_evidence_id: str
    historical_execution_evidence_id: str
    source_capture_evidence_id: str
    target_period: str
    source_period: str
    forecast_origin: datetime
    frozen_at: datetime
    source_receipt_no: str
    source_receipt_date: date
    source_available_at: datetime
    source_raw_payload_sha256: str
    source_captured_payload_bytes_sha256: str
    predictors: tuple[str, ...]
    feature_values: tuple[float, ...]
    status: str = _VECTOR_STATUS
    prospective_feature_vector_frozen: bool = True
    prospective_forecast_run: bool = False
    q1_used_for_selection: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    q3_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.contract_evidence_id,
            self.protocol_evidence_id,
            self.selected_estimator_evidence_id,
            self.historical_execution_evidence_id,
            self.source_capture_evidence_id,
            self.source_raw_payload_sha256,
            self.source_captured_payload_bytes_sha256,
        ):
            if not _valid_sha(value):
                raise ValueError("Prospective feature vector evidence/hash must be SHA-256")
        if self.status != _VECTOR_STATUS:
            raise ValueError("Prospective feature vector status drifted")
        if self.target_period != _EXPECTED_TARGET_PERIOD or self.source_period != _EXPECTED_SOURCE_PERIOD:
            raise ValueError("Prospective feature vector period mapping drifted")
        if self.predictors != _EXPECTED_PREDICTORS or len(self.feature_values) != 1:
            raise ValueError("Prospective feature vector predictor geometry drifted")
        if not all(math.isfinite(value) for value in self.feature_values):
            raise ValueError("Prospective feature vector contains non-finite values")
        if self.source_receipt_date != _receipt_date(self.source_receipt_no):
            raise ValueError("Prospective feature vector receipt/date drifted")
        if _aware_kst(self.source_available_at, "source_available_at") > _aware_kst(
            self.frozen_at, "frozen_at"
        ):
            raise ValueError("Prospective feature source was unavailable when frozen")
        if _aware_kst(self.frozen_at, "frozen_at") > _aware_kst(
            self.forecast_origin, "forecast_origin"
        ):
            raise ValueError("Prospective feature vector was frozen after forecast origin")
        if not self.prospective_feature_vector_frozen:
            raise ValueError("Prospective feature vector did not record freeze boundary")
        if any(
            (
                self.prospective_forecast_run,
                self.q1_used_for_selection,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.q3_evaluated,
                self.numeric_forward_forecast_enabled,
            )
        ):
            raise ValueError("Prospective feature vector opened protected outcome/forecast state")


def _feature_vector_payload(item: FrozenProspectiveFeatureVector) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "protocol_evidence_id": item.protocol_evidence_id,
        "selected_estimator_evidence_id": item.selected_estimator_evidence_id,
        "historical_execution_evidence_id": item.historical_execution_evidence_id,
        "source_capture_evidence_id": item.source_capture_evidence_id,
        "target_period": item.target_period,
        "source_period": item.source_period,
        "forecast_origin": item.forecast_origin.isoformat(),
        "frozen_at": item.frozen_at.isoformat(),
        "source_receipt_no": item.source_receipt_no,
        "source_receipt_date": item.source_receipt_date.isoformat(),
        "source_available_at": item.source_available_at.isoformat(),
        "source_raw_payload_sha256": item.source_raw_payload_sha256,
        "source_captured_payload_bytes_sha256": item.source_captured_payload_bytes_sha256,
        "predictors": list(item.predictors),
        "feature_values": list(item.feature_values),
        "status": item.status,
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "q1_used_for_selection": item.q1_used_for_selection,
        "q3_target_read": item.q3_target_read,
        "q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
    }


def build_prospective_feature_vector(
    contract: ProspectiveFeatureFreezeContract,
    selected: FrozenSelectedEstimatorFullFit,
    *,
    protocol_evidence_id: str,
    historical_execution_evidence_id: str,
    capture: ProspectiveSourceCapture,
    raw_payload: object,
    revenue_account_ids: tuple[str, ...],
    cost_of_sales_account_ids: tuple[str, ...],
    gross_profit_account_ids: tuple[str, ...],
) -> FrozenProspectiveFeatureVector:
    if selected.selected_candidate_id != contract.required_selected_candidate_id:
        raise ValueError("Prospective feature selected candidate binding drifted")
    if selected.predictors != contract.required_predictors:
        raise ValueError("Prospective feature selected predictor binding drifted")
    if selected.execution_evidence_id != historical_execution_evidence_id:
        raise ValueError("Prospective feature historical execution binding drifted")
    if capture.contract_evidence_id != contract.evidence_id:
        raise ValueError("Prospective feature source capture contract binding drifted")
    if capture.historical_execution_evidence_id != historical_execution_evidence_id:
        raise ValueError("Prospective feature source capture execution binding drifted")
    if _sha(raw_payload) != capture.raw_payload_sha256:
        raise ValueError("Prospective feature raw payload does not match locked capture")
    if _sha_bytes(_canonical_bytes(raw_payload)) != capture.captured_payload_bytes_sha256:
        raise ValueError("Prospective feature raw bytes do not match locked capture")

    rows = _financial_rows(raw_payload)
    revenue, revenue_receipt = _select_account(
        rows,
        revenue_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="revenue",
    )
    cost, cost_receipt = _select_account(
        rows,
        cost_of_sales_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="cost_of_sales",
    )
    gross, gross_receipt = _select_account(
        rows,
        gross_profit_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    if len(receipts) != 1:
        raise ValueError("Prospective source accounts cross filing receipts")
    receipt = next(iter(receipts))
    available = _source_available_at(receipt)
    if available > capture.captured_at:
        raise ValueError("Prospective source filing was unavailable at raw capture time")
    if available > capture.forecast_origin:
        raise ValueError("Prospective source filing was unavailable by forecast origin")
    if revenue - cost != gross:
        raise ValueError("Prospective source accounting identity failed")

    value = gross / 1_000_000.0
    provisional = FrozenProspectiveFeatureVector(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        protocol_evidence_id=protocol_evidence_id,
        selected_estimator_evidence_id=selected.evidence_id,
        historical_execution_evidence_id=historical_execution_evidence_id,
        source_capture_evidence_id=capture.evidence_id,
        target_period=contract.target_period,
        source_period=contract.source_period,
        forecast_origin=capture.forecast_origin,
        frozen_at=capture.captured_at,
        source_receipt_no=receipt,
        source_receipt_date=_receipt_date(receipt),
        source_available_at=available,
        source_raw_payload_sha256=capture.raw_payload_sha256,
        source_captured_payload_bytes_sha256=capture.captured_payload_bytes_sha256,
        predictors=selected.predictors,
        feature_values=(value,),
    )
    return replace(provisional, evidence_id=_sha(_feature_vector_payload(provisional)))


def persist_prospective_feature_vector(
    item: FrozenProspectiveFeatureVector,
    *,
    output: str | Path = DEFAULT_2026Q3_PROSPECTIVE_OUTPUT,
) -> Path:
    if _sha(_feature_vector_payload(item)) != item.evidence_id:
        raise ValueError("Prospective feature vector evidence hash drifted")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _VECTOR_STATUS,
        "feature_vector": {"evidence_id": item.evidence_id, **_feature_vector_payload(item)},
    }
    encoded = _canonical_bytes(payload)
    immutable = root / f"feature-vector-{item.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("Prospective feature vector immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_feature_vector.json"
    if pointer.exists() and pointer.read_bytes() != encoded:
        raise ValueError("Prospective feature vector is already locked to different evidence")
    temporary = root / ".latest_feature_vector.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def load_prospective_feature_vector(
    path: str | Path = DEFAULT_2026Q3_FEATURE_VECTOR,
) -> FrozenProspectiveFeatureVector:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Prospective feature vector artifact")
    if root.get("schema_version") != 1 or root.get("status") != _VECTOR_STATUS:
        raise ValueError("Prospective feature vector artifact status is invalid")
    body = _mapping(root.get("feature_vector"), "Prospective feature vector body")
    item = FrozenProspectiveFeatureVector(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        protocol_evidence_id=str(body.get("protocol_evidence_id", "")),
        selected_estimator_evidence_id=str(body.get("selected_estimator_evidence_id", "")),
        historical_execution_evidence_id=str(
            body.get("historical_execution_evidence_id", "")
        ),
        source_capture_evidence_id=str(body.get("source_capture_evidence_id", "")),
        target_period=str(body.get("target_period", "")),
        source_period=str(body.get("source_period", "")),
        forecast_origin=datetime.fromisoformat(str(body.get("forecast_origin", ""))),
        frozen_at=datetime.fromisoformat(str(body.get("frozen_at", ""))),
        source_receipt_no=str(body.get("source_receipt_no", "")),
        source_receipt_date=date.fromisoformat(str(body.get("source_receipt_date", ""))),
        source_available_at=datetime.fromisoformat(str(body.get("source_available_at", ""))),
        source_raw_payload_sha256=str(body.get("source_raw_payload_sha256", "")),
        source_captured_payload_bytes_sha256=str(
            body.get("source_captured_payload_bytes_sha256", "")
        ),
        predictors=tuple(str(value) for value in _array(body.get("predictors"), "predictors")),
        feature_values=tuple(
            float(str(value)) for value in _array(body.get("feature_values"), "feature_values")
        ),
        status=str(body.get("status", "")),
        prospective_feature_vector_frozen=(body.get("prospective_feature_vector_frozen") is True),
        prospective_forecast_run=body.get("prospective_forecast_run") is True,
        q1_used_for_selection=body.get("q1_used_for_selection") is True,
        q3_target_read=body.get("q3_target_read") is True,
        q3_source_outcome_loaded=body.get("q3_source_outcome_loaded") is True,
        q3_evaluated=body.get("q3_evaluated") is True,
        numeric_forward_forecast_enabled=(body.get("numeric_forward_forecast_enabled") is True),
    )
    if _sha(_feature_vector_payload(item)) != item.evidence_id:
        raise ValueError("Prospective feature vector evidence hash mismatch")
    return item


def collect_2026q2_source_payload(
    client: OpenDartReadOnlyClient,
    contract: ProspectiveFeatureFreezeContract,
) -> object:
    corp = client.resolve_stock_codes([contract.ticker])[contract.ticker]
    batch = client.financial_statements(
        corp,
        business_year=contract.business_year,
        report_code=contract.report_code,
        fs_div=contract.fs_div,
    )
    if batch.corp.stock_code != contract.ticker:
        raise ValueError("Prospective OpenDART batch ticker drifted")
    return batch.raw_payload


def freeze_2026q3_prospective_feature_vector(
    client: OpenDartReadOnlyClient,
    *,
    captured_at: datetime | None = None,
    contract_path: str | Path = DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT,
    output: str | Path = DEFAULT_2026Q3_PROSPECTIVE_OUTPUT,
) -> tuple[FrozenProspectiveFeatureVector, ProspectiveSourceCapture, bool, bool]:
    contract = load_prospective_feature_freeze_contract(contract_path)
    protocol = load_frozen_company_gp_ex_ante_protocol(contract.protocol_path)
    selected = load_selected_estimator_artifact(contract.selected_estimator_path)
    repair = load_frozen_historical_schema_repair_v2(contract.historical_execution_v2_path)
    execution = repair.runtime_execution

    if selected.execution_evidence_id != execution.evidence_id:
        raise ValueError("Prospective feature selected estimator/execution binding drifted")
    if selected.selected_candidate_id != contract.required_selected_candidate_id:
        raise ValueError("Prospective feature selected candidate does not match contract")
    if selected.predictors != contract.required_predictors:
        raise ValueError("Prospective feature selected predictors do not match contract")
    if any(
        (
            selected.prospective_feature_vector_frozen,
            selected.prospective_forecast_run,
            selected.q3_target_read,
            selected.q3_source_outcome_loaded,
            selected.q3_evaluated,
            selected.numeric_forward_forecast_enabled,
        )
    ):
        raise ValueError("Prospective feature selected estimator artifact opened future state")

    forecast_origin = protocol.origin_for(contract.target_period)
    root = Path(output)
    feature_pointer = root / "latest_feature_vector.json"
    source_pointer = root / "latest_source_capture.json"
    feature_reused = feature_pointer.is_file()
    if feature_reused:
        item = load_prospective_feature_vector(feature_pointer)
        capture, _payload = load_prospective_source_capture(source_pointer)
        if item.contract_evidence_id != contract.evidence_id:
            raise ValueError("Locked prospective feature vector belongs to another contract")
        if item.selected_estimator_evidence_id != selected.evidence_id:
            raise ValueError("Locked prospective feature vector selected estimator drifted")
        if capture.evidence_id != item.source_capture_evidence_id:
            raise ValueError("Locked prospective feature/source capture binding drifted")
        return item, capture, True, True

    source_reused = source_pointer.is_file()
    if source_reused:
        capture, raw_payload = load_prospective_source_capture(source_pointer)
        if capture.contract_evidence_id != contract.evidence_id:
            raise ValueError("Locked prospective source capture belongs to another contract")
        if capture.historical_execution_evidence_id != execution.evidence_id:
            raise ValueError("Locked prospective source capture execution drifted")
    else:
        now = _aware_kst(
            captured_at if captured_at is not None else datetime.now(_KOREA_TZ),
            "Prospective source captured_at",
        )
        if now > forecast_origin:
            raise ValueError(
                "2026Q3 forecast origin was missed before first source capture; use frozen fallback 2026Q4"
            )
        raw_payload = collect_2026q2_source_payload(client, contract)
        capture = build_prospective_source_capture(
            contract,
            historical_execution_evidence_id=execution.evidence_id,
            forecast_origin=forecast_origin,
            captured_at=now,
            raw_payload=raw_payload,
        )
        persist_prospective_source_capture(capture, raw_payload, output=root)

    item = build_prospective_feature_vector(
        contract,
        selected,
        protocol_evidence_id=protocol.evidence_id,
        historical_execution_evidence_id=execution.evidence_id,
        capture=capture,
        raw_payload=raw_payload,
        revenue_account_ids=execution.revenue_account_ids,
        cost_of_sales_account_ids=execution.cost_of_sales_account_ids,
        gross_profit_account_ids=execution.gross_profit_account_ids,
    )
    persist_prospective_feature_vector(item, output=root)
    return item, capture, source_reused, False


__all__ = [
    "DEFAULT_2026Q3_FEATURE_VECTOR",
    "DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT",
    "DEFAULT_2026Q3_PROSPECTIVE_OUTPUT",
    "DEFAULT_2026Q3_SOURCE_CAPTURE",
    "FrozenProspectiveFeatureVector",
    "ProspectiveFeatureFreezeContract",
    "ProspectiveSourceCapture",
    "build_prospective_feature_vector",
    "build_prospective_source_capture",
    "collect_2026q2_source_payload",
    "freeze_2026q3_prospective_feature_vector",
    "load_prospective_feature_freeze_contract",
    "load_prospective_feature_vector",
    "load_prospective_source_capture",
    "load_selected_estimator_artifact",
    "persist_prospective_feature_vector",
    "persist_prospective_source_capture",
]
