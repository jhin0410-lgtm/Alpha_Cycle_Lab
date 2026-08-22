"""Preregister and execute outcome scoring for the locked SK hynix 2026Q3 GP forecast.

The scoring contract is frozen before the 2026Q3 outcome exists. The eventual scoring path
may only acquire the exact 2026Q3 OpenDART filing defined by the historical v2 source policy,
lock source bytes before account extraction, and compare the immutable selected forecast with
the immutable persistence benchmark using strict absolute error. It cannot refit or redesign
the model.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast import (
    LockedNumericForecast,
    load_locked_numeric_forecast,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    FrozenHistoricalEvaluationExecution,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation_v2 import (
    load_frozen_historical_schema_repair_v2,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT = Path(
    "config/skhynix_company_gp_ex_ante_2026q3_outcome_scoring.v1.yaml"
)
DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-outcome-score"
)
DEFAULT_2026Q3_OUTCOME_SOURCE_CAPTURE = (
    DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT / "latest_outcome_source_capture.json"
)
DEFAULT_2026Q3_OUTCOME_SCORE = (
    DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT / "latest_outcome_score.json"
)
_CAPTURE_STATUS = "skhynix_ex_ante_2026q3_outcome_source_locked_pre_extraction"
_SCORE_STATUS = "skhynix_ex_ante_2026q3_locked_forecast_scored"
_EXPECTED_TARGET_PERIOD = "2026Q3"
_EXPECTED_REPORT_CODE = "11014"
_EXPECTED_BENCHMARK = "previous_reported_quarter_gross_profit_persistence"
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})


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


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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


def _receipt_date(receipt: str) -> date:
    if len(receipt) != 14 or not receipt.isdigit():
        raise ValueError("2026Q3 outcome receipt number must be fourteen digits")
    return date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"2026Q3 outcome {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"2026Q3 outcome {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"2026Q3 outcome {label} must be integral KRW")
    return int(amount)


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    root = _mapping(raw_payload, "2026Q3 OpenDART raw payload")
    financials = _mapping(root.get("financials"), "2026Q3 OpenDART financials")
    raw_rows = _array(financials.get("list"), "2026Q3 OpenDART financial list")
    return tuple(_mapping(item, "2026Q3 OpenDART financial row") for item in raw_rows)


@dataclass(frozen=True)
class OutcomeScoringContract:
    evidence_id: str
    scoring_version: str
    status: str
    ticker: str
    target_metric: str
    target_period: str
    numeric_forecast_path: str
    historical_execution_v2_path: str
    business_year: int
    report_code: str
    fs_div: str
    amount_field: str
    primary_metric: str
    winner_rule: str
    minimum_evaluation_date: date

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("2026Q3 scoring contract evidence id must be SHA-256")
        if self.scoring_version != "1.0-frozen-before-2026q3-outcome":
            raise ValueError("2026Q3 scoring contract version drifted")
        if self.status != "frozen_before_2026q3_outcome":
            raise ValueError("2026Q3 scoring contract status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("2026Q3 scoring contract ticker/target drifted")
        if self.target_period != _EXPECTED_TARGET_PERIOD:
            raise ValueError("2026Q3 scoring target period drifted")
        if self.business_year != 2026 or self.report_code != _EXPECTED_REPORT_CODE:
            raise ValueError("2026Q3 scoring filing geometry drifted")
        if self.fs_div != "CFS" or self.amount_field != "thstrm_amount":
            raise ValueError("2026Q3 scoring source semantics drifted")
        if self.primary_metric != "absolute_error_krw_million":
            raise ValueError("2026Q3 scoring primary metric drifted")
        if self.winner_rule != "strict_lower_absolute_error":
            raise ValueError("2026Q3 scoring winner rule drifted")
        if self.minimum_evaluation_date != date(2026, 9, 30):
            raise ValueError("2026Q3 scoring minimum evaluation date drifted")


def load_outcome_scoring_contract(
    path: str | Path = DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT,
) -> OutcomeScoringContract:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "2026Q3 scoring manifest")
    if root.get("schema_version") != 1:
        raise ValueError("2026Q3 scoring manifest schema is invalid")
    body = _mapping(root.get("scoring"), "2026Q3 scoring body")
    if body.get("scoring_id") != "skhynix_company_gp_ex_ante_2026q3_outcome_scoring":
        raise ValueError("2026Q3 scoring id drifted")
    inputs = _mapping(body.get("locked_inputs"), "2026Q3 scoring locked inputs")
    source = _mapping(body.get("target_source_policy"), "2026Q3 scoring source policy")
    timing = _mapping(body.get("timing_policy"), "2026Q3 scoring timing policy")
    score = _mapping(body.get("frozen_score_definition"), "2026Q3 score definition")
    post = _mapping(body.get("post_score_boundary"), "2026Q3 post-score boundary")

    expected_source = {
        "provider": "opendart",
        "endpoint": "fnlttSinglAcntAll",
        "account_alias_policy_source": "historical_execution_v2",
        "allowed_statement_divisions_source": "historical_execution_v2",
        "require_revenue_minus_cost_equals_gross_profit": True,
        "require_same_receipt_for_selected_accounts": True,
        "require_receipt_date_not_after_evaluation_date": True,
        "raw_payload_capture_before_target_extraction": True,
        "raw_payload_refresh_after_first_successful_capture_allowed": False,
        "account_name_fuzzy_matching_allowed": False,
        "arithmetic_derivation_of_missing_source_accounts_allowed": False,
        "source_fallback_allowed": False,
        "correction_search_or_selection_allowed": False,
        "partial_target_acceptance_allowed": False,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise ValueError(f"2026Q3 scoring source policy drifted: {key}")

    expected_score = {
        "selected_error_sign_convention": "forecast_minus_actual",
        "benchmark_error_sign_convention": "forecast_minus_actual",
        "selected_absolute_error_rule": "abs_selected_signed_error",
        "benchmark_absolute_error_rule": "abs_benchmark_signed_error",
        "exact_absolute_error_tie_result": "tie",
        "tolerance_based_tie_allowed": False,
        "post_outcome_metric_addition_allowed": False,
        "post_outcome_metric_reweighting_allowed": False,
        "historical_mae_used_as_pass_fail_threshold": False,
        "relative_error_primary_metric_allowed": False,
    }
    for key, expected in expected_score.items():
        if score.get(key) != expected:
            raise ValueError(f"2026Q3 scoring definition drifted: {key}")

    expected_post_false = (
        "model_refit_allowed",
        "coefficient_change_allowed",
        "predictor_change_allowed",
        "feature_change_allowed",
        "benchmark_change_allowed",
        "target_source_refresh_allowed",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
        "investment_action_enabled",
    )
    if any(post.get(key) is not False for key in expected_post_false):
        raise ValueError("2026Q3 scoring contract opened a prohibited post-score path")
    expected_post_true = (
        "2026q3_target_read_after_successful_score",
        "2026q3_source_outcome_loaded_after_successful_score",
        "2026q3_evaluated_after_successful_score",
        "prospective_forecast_remains_immutable",
    )
    if any(post.get(key) is not True for key in expected_post_true):
        raise ValueError("2026Q3 scoring contract post-score flags drifted")
    if timing.get("target_period_must_be_complete_before_acquisition") is not True:
        raise ValueError("2026Q3 scoring period-complete gate drifted")
    if timing.get("evaluation_date_must_not_precede_target_period_end") is not True:
        raise ValueError("2026Q3 scoring evaluation-date gate drifted")
    if timing.get("caller_must_supply_evaluation_date") is not True:
        raise ValueError("2026Q3 scoring explicit evaluation-date gate drifted")
    if timing.get("failed_or_empty_preavailability_response_must_not_be_persisted_as_outcome") is not True:
        raise ValueError("2026Q3 scoring empty-response policy drifted")

    stable = {"schema_version": 1, "scoring": body}
    return OutcomeScoringContract(
        evidence_id=_sha(stable),
        scoring_version=str(body.get("scoring_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        target_period=str(body.get("target_period", "")),
        numeric_forecast_path=str(inputs.get("numeric_forecast_path", "")),
        historical_execution_v2_path=str(inputs.get("historical_execution_v2_path", "")),
        business_year=int(str(source.get("business_year", -1))),
        report_code=str(source.get("report_code", "")),
        fs_div=str(source.get("fs_div", "")),
        amount_field=str(source.get("current_term_amount_field", "")),
        primary_metric=str(score.get("primary_metric", "")),
        winner_rule=str(score.get("winner_rule", "")),
        minimum_evaluation_date=date.fromisoformat(str(timing.get("target_period_end_date", ""))),
    )


@dataclass(frozen=True)
class OutcomeSourceCapture:
    evidence_id: str
    contract_evidence_id: str
    forecast_evidence_id: str
    historical_execution_evidence_id: str
    evaluation_date: date
    target_period: str
    raw_payload_sha256: str
    captured_payload_bytes_sha256: str
    status: str = _CAPTURE_STATUS

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.contract_evidence_id,
            self.forecast_evidence_id,
            self.historical_execution_evidence_id,
            self.raw_payload_sha256,
            self.captured_payload_bytes_sha256,
        ):
            if not _valid_sha(value):
                raise ValueError("2026Q3 outcome source capture hashes must be SHA-256")
        if self.status != _CAPTURE_STATUS or self.target_period != _EXPECTED_TARGET_PERIOD:
            raise ValueError("2026Q3 outcome source capture status/period drifted")
        if self.evaluation_date < date(2026, 9, 30):
            raise ValueError("2026Q3 outcome source capture predates quarter end")


def _capture_payload(item: OutcomeSourceCapture) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "forecast_evidence_id": item.forecast_evidence_id,
        "historical_execution_evidence_id": item.historical_execution_evidence_id,
        "evaluation_date": item.evaluation_date.isoformat(),
        "target_period": item.target_period,
        "raw_payload_sha256": item.raw_payload_sha256,
        "captured_payload_bytes_sha256": item.captured_payload_bytes_sha256,
        "status": item.status,
    }


def build_outcome_source_capture(
    contract: OutcomeScoringContract,
    forecast: LockedNumericForecast,
    execution: FrozenHistoricalEvaluationExecution,
    *,
    evaluation_date: date,
    raw_payload: object,
) -> OutcomeSourceCapture:
    if evaluation_date < contract.minimum_evaluation_date:
        raise ValueError("2026Q3 outcome acquisition is prohibited before quarter end")
    if forecast.target_period != contract.target_period:
        raise ValueError("2026Q3 outcome forecast target period drifted")
    if execution.evidence_id != forecast_selected_execution_evidence(contract, execution):
        raise ValueError("2026Q3 outcome historical execution binding drifted")
    if not _financial_rows(raw_payload):
        raise ValueError("2026Q3 outcome source is not available; empty payload is not persisted")
    encoded = _canonical_bytes(raw_payload)
    provisional = OutcomeSourceCapture(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        forecast_evidence_id=forecast.evidence_id,
        historical_execution_evidence_id=execution.evidence_id,
        evaluation_date=evaluation_date,
        target_period=contract.target_period,
        raw_payload_sha256=_sha(raw_payload),
        captured_payload_bytes_sha256=_sha_bytes(encoded),
    )
    return replace(provisional, evidence_id=_sha(_capture_payload(provisional)))


def forecast_selected_execution_evidence(
    contract: OutcomeScoringContract,
    execution: FrozenHistoricalEvaluationExecution,
) -> str:
    repair = load_frozen_historical_schema_repair_v2(contract.historical_execution_v2_path)
    if repair.runtime_execution.evidence_id != execution.evidence_id:
        raise ValueError("2026Q3 scoring historical v2 execution replay drifted")
    return repair.evidence_id


def persist_outcome_source_capture(
    item: OutcomeSourceCapture,
    raw_payload: object,
    *,
    output: str | Path = DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT,
) -> Path:
    if _sha(_capture_payload(item)) != item.evidence_id:
        raise ValueError("2026Q3 outcome source capture evidence hash drifted")
    if _sha(raw_payload) != item.raw_payload_sha256:
        raise ValueError("2026Q3 outcome source raw payload hash drifted")
    encoded_raw = _canonical_bytes(raw_payload)
    if _sha_bytes(encoded_raw) != item.captured_payload_bytes_sha256:
        raise ValueError("2026Q3 outcome source captured bytes drifted")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _CAPTURE_STATUS,
        "capture": {"evidence_id": item.evidence_id, **_capture_payload(item)},
        "raw_payload": raw_payload,
    }
    encoded = _canonical_bytes(payload)
    immutable = root / f"outcome-source-{item.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("2026Q3 outcome source immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_outcome_source_capture.json"
    if pointer.exists() and pointer.read_bytes() != encoded:
        raise ValueError("2026Q3 outcome source is already locked to different evidence")
    temporary = root / ".latest_outcome_source_capture.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def load_outcome_source_capture(
    path: str | Path = DEFAULT_2026Q3_OUTCOME_SOURCE_CAPTURE,
) -> tuple[OutcomeSourceCapture, object]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "2026Q3 outcome source artifact")
    if root.get("schema_version") != 1 or root.get("status") != _CAPTURE_STATUS:
        raise ValueError("2026Q3 outcome source artifact status is invalid")
    body = _mapping(root.get("capture"), "2026Q3 outcome source capture")
    item = OutcomeSourceCapture(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        forecast_evidence_id=str(body.get("forecast_evidence_id", "")),
        historical_execution_evidence_id=str(
            body.get("historical_execution_evidence_id", "")
        ),
        evaluation_date=date.fromisoformat(str(body.get("evaluation_date", ""))),
        target_period=str(body.get("target_period", "")),
        raw_payload_sha256=str(body.get("raw_payload_sha256", "")),
        captured_payload_bytes_sha256=str(body.get("captured_payload_bytes_sha256", "")),
        status=str(body.get("status", "")),
    )
    raw_payload = root.get("raw_payload")
    if _sha(_capture_payload(item)) != item.evidence_id:
        raise ValueError("2026Q3 outcome source capture evidence mismatch")
    if _sha(raw_payload) != item.raw_payload_sha256:
        raise ValueError("2026Q3 outcome source raw payload mismatch")
    if _sha_bytes(_canonical_bytes(raw_payload)) != item.captured_payload_bytes_sha256:
        raise ValueError("2026Q3 outcome source captured bytes mismatch")
    return item, raw_payload


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
            f"2026Q3 outcome account must resolve uniquely: label={label} count={len(unique)}"
        )
    return unique[0]


@dataclass(frozen=True)
class OutcomeObservation:
    source_capture_evidence_id: str
    receipt_no: str
    receipt_date: date
    revenue_krw: int
    cost_of_sales_krw: int
    gross_profit_krw: int
    gross_profit_krw_million: float

    def __post_init__(self) -> None:
        if not _valid_sha(self.source_capture_evidence_id):
            raise ValueError("2026Q3 outcome observation capture evidence is invalid")
        if self.receipt_date != _receipt_date(self.receipt_no):
            raise ValueError("2026Q3 outcome receipt/date identity drifted")
        if self.revenue_krw <= 0 or self.cost_of_sales_krw < 0:
            raise ValueError("2026Q3 outcome revenue/cost is invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("2026Q3 outcome accounting identity failed")
        if self.gross_profit_krw_million != self.gross_profit_krw / 1_000_000.0:
            raise ValueError("2026Q3 outcome million-unit conversion drifted")


def extract_outcome_observation(
    contract: OutcomeScoringContract,
    execution: FrozenHistoricalEvaluationExecution,
    capture: OutcomeSourceCapture,
    raw_payload: object,
) -> OutcomeObservation:
    if capture.contract_evidence_id != contract.evidence_id:
        raise ValueError("2026Q3 outcome capture belongs to another scoring contract")
    if capture.historical_execution_evidence_id != execution.evidence_id:
        raise ValueError("2026Q3 outcome capture historical execution drifted")
    if _sha(raw_payload) != capture.raw_payload_sha256:
        raise ValueError("2026Q3 outcome raw payload does not match locked capture")
    rows = _financial_rows(raw_payload)
    revenue, revenue_receipt = _select_account(
        rows,
        execution.revenue_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="revenue",
    )
    cost, cost_receipt = _select_account(
        rows,
        execution.cost_of_sales_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="cost_of_sales",
    )
    gross, gross_receipt = _select_account(
        rows,
        execution.gross_profit_account_ids,
        business_year=contract.business_year,
        report_code=contract.report_code,
        amount_field=contract.amount_field,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    if len(receipts) != 1:
        raise ValueError("2026Q3 outcome selected accounts cross filing receipts")
    receipt = next(iter(receipts))
    receipt_day = _receipt_date(receipt)
    if receipt_day > capture.evaluation_date:
        raise ValueError("2026Q3 outcome filing is later than the locked evaluation date")
    if revenue - cost != gross:
        raise ValueError("2026Q3 outcome accounting identity failed")
    return OutcomeObservation(
        source_capture_evidence_id=capture.evidence_id,
        receipt_no=receipt,
        receipt_date=receipt_day,
        revenue_krw=revenue,
        cost_of_sales_krw=cost,
        gross_profit_krw=gross,
        gross_profit_krw_million=gross / 1_000_000.0,
    )


@dataclass(frozen=True)
class ProspectiveOutcomeScore:
    evidence_id: str
    contract_evidence_id: str
    forecast_evidence_id: str
    source_capture_evidence_id: str
    historical_execution_evidence_id: str
    evaluation_date: date
    target_period: str
    target_receipt_no: str
    actual_krw_million: float
    selected_forecast_krw_million: float
    benchmark_forecast_krw_million: float
    selected_signed_error_krw_million: float
    benchmark_signed_error_krw_million: float
    selected_absolute_error_krw_million: float
    benchmark_absolute_error_krw_million: float
    absolute_error_advantage_krw_million: float
    winner: str
    status: str = _SCORE_STATUS
    q3_target_read: bool = True
    q3_source_outcome_loaded: bool = True
    q3_evaluated: bool = True
    model_refit_run: bool = False
    forecast_changed_after_lock: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.contract_evidence_id,
            self.forecast_evidence_id,
            self.source_capture_evidence_id,
            self.historical_execution_evidence_id,
        ):
            if not _valid_sha(value):
                raise ValueError("2026Q3 outcome score evidence ids must be SHA-256")
        if self.status != _SCORE_STATUS or self.target_period != _EXPECTED_TARGET_PERIOD:
            raise ValueError("2026Q3 outcome score status/period drifted")
        numbers = (
            self.actual_krw_million,
            self.selected_forecast_krw_million,
            self.benchmark_forecast_krw_million,
            self.selected_signed_error_krw_million,
            self.benchmark_signed_error_krw_million,
            self.selected_absolute_error_krw_million,
            self.benchmark_absolute_error_krw_million,
            self.absolute_error_advantage_krw_million,
        )
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("2026Q3 outcome score contains non-finite values")
        expected_winner = (
            "selected"
            if self.selected_absolute_error_krw_million
            < self.benchmark_absolute_error_krw_million
            else "benchmark"
            if self.selected_absolute_error_krw_million
            > self.benchmark_absolute_error_krw_million
            else "tie"
        )
        if self.winner != expected_winner:
            raise ValueError("2026Q3 outcome winner flag drifted")
        if not (self.q3_target_read and self.q3_source_outcome_loaded and self.q3_evaluated):
            raise ValueError("2026Q3 outcome score did not record boundary crossing")
        if self.model_refit_run or self.forecast_changed_after_lock:
            raise ValueError("2026Q3 outcome scoring changed the frozen forecast/model")


def _score_payload(item: ProspectiveOutcomeScore) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "forecast_evidence_id": item.forecast_evidence_id,
        "source_capture_evidence_id": item.source_capture_evidence_id,
        "historical_execution_evidence_id": item.historical_execution_evidence_id,
        "evaluation_date": item.evaluation_date.isoformat(),
        "target_period": item.target_period,
        "target_receipt_no": item.target_receipt_no,
        "actual_krw_million": item.actual_krw_million,
        "selected_forecast_krw_million": item.selected_forecast_krw_million,
        "benchmark_forecast_krw_million": item.benchmark_forecast_krw_million,
        "selected_signed_error_krw_million": item.selected_signed_error_krw_million,
        "benchmark_signed_error_krw_million": item.benchmark_signed_error_krw_million,
        "selected_absolute_error_krw_million": item.selected_absolute_error_krw_million,
        "benchmark_absolute_error_krw_million": item.benchmark_absolute_error_krw_million,
        "absolute_error_advantage_krw_million": item.absolute_error_advantage_krw_million,
        "winner": item.winner,
        "status": item.status,
        "q3_target_read": item.q3_target_read,
        "q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "q3_evaluated": item.q3_evaluated,
        "model_refit_run": item.model_refit_run,
        "forecast_changed_after_lock": item.forecast_changed_after_lock,
    }


def build_outcome_score(
    contract: OutcomeScoringContract,
    forecast: LockedNumericForecast,
    capture: OutcomeSourceCapture,
    observation: OutcomeObservation,
) -> ProspectiveOutcomeScore:
    if capture.forecast_evidence_id != forecast.evidence_id:
        raise ValueError("2026Q3 outcome source/forecast binding drifted")
    if observation.source_capture_evidence_id != capture.evidence_id:
        raise ValueError("2026Q3 outcome observation/capture binding drifted")
    if forecast.benchmark_id != _EXPECTED_BENCHMARK:
        raise ValueError("2026Q3 outcome benchmark id drifted")
    if forecast.q3_target_read or forecast.q3_source_outcome_loaded or forecast.q3_evaluated:
        raise ValueError("2026Q3 locked forecast was not outcome-blind")
    actual = observation.gross_profit_krw_million
    selected_signed = forecast.selected_forecast_krw_million - actual
    benchmark_signed = forecast.benchmark_forecast_krw_million - actual
    selected_abs = abs(selected_signed)
    benchmark_abs = abs(benchmark_signed)
    winner = (
        "selected"
        if selected_abs < benchmark_abs
        else "benchmark"
        if selected_abs > benchmark_abs
        else "tie"
    )
    provisional = ProspectiveOutcomeScore(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        forecast_evidence_id=forecast.evidence_id,
        source_capture_evidence_id=capture.evidence_id,
        historical_execution_evidence_id=capture.historical_execution_evidence_id,
        evaluation_date=capture.evaluation_date,
        target_period=contract.target_period,
        target_receipt_no=observation.receipt_no,
        actual_krw_million=actual,
        selected_forecast_krw_million=forecast.selected_forecast_krw_million,
        benchmark_forecast_krw_million=forecast.benchmark_forecast_krw_million,
        selected_signed_error_krw_million=selected_signed,
        benchmark_signed_error_krw_million=benchmark_signed,
        selected_absolute_error_krw_million=selected_abs,
        benchmark_absolute_error_krw_million=benchmark_abs,
        absolute_error_advantage_krw_million=benchmark_abs - selected_abs,
        winner=winner,
    )
    return replace(provisional, evidence_id=_sha(_score_payload(provisional)))


def persist_outcome_score(
    item: ProspectiveOutcomeScore,
    *,
    output: str | Path = DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT,
) -> Path:
    if _sha(_score_payload(item)) != item.evidence_id:
        raise ValueError("2026Q3 outcome score evidence hash drifted")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _SCORE_STATUS,
        "score": {"evidence_id": item.evidence_id, **_score_payload(item)},
    }
    encoded = _canonical_bytes(payload)
    immutable = root / f"outcome-score-{item.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("2026Q3 outcome score immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_outcome_score.json"
    if pointer.exists() and pointer.read_bytes() != encoded:
        raise ValueError("2026Q3 outcome score is already locked to different evidence")
    temporary = root / ".latest_outcome_score.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def load_outcome_score(
    path: str | Path = DEFAULT_2026Q3_OUTCOME_SCORE,
) -> ProspectiveOutcomeScore:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "2026Q3 outcome score artifact")
    if root.get("schema_version") != 1 or root.get("status") != _SCORE_STATUS:
        raise ValueError("2026Q3 outcome score artifact status is invalid")
    body = _mapping(root.get("score"), "2026Q3 outcome score body")
    item = ProspectiveOutcomeScore(
        evidence_id=str(body.get("evidence_id", "")),
        contract_evidence_id=str(body.get("contract_evidence_id", "")),
        forecast_evidence_id=str(body.get("forecast_evidence_id", "")),
        source_capture_evidence_id=str(body.get("source_capture_evidence_id", "")),
        historical_execution_evidence_id=str(
            body.get("historical_execution_evidence_id", "")
        ),
        evaluation_date=date.fromisoformat(str(body.get("evaluation_date", ""))),
        target_period=str(body.get("target_period", "")),
        target_receipt_no=str(body.get("target_receipt_no", "")),
        actual_krw_million=float(str(body.get("actual_krw_million", "nan"))),
        selected_forecast_krw_million=float(
            str(body.get("selected_forecast_krw_million", "nan"))
        ),
        benchmark_forecast_krw_million=float(
            str(body.get("benchmark_forecast_krw_million", "nan"))
        ),
        selected_signed_error_krw_million=float(
            str(body.get("selected_signed_error_krw_million", "nan"))
        ),
        benchmark_signed_error_krw_million=float(
            str(body.get("benchmark_signed_error_krw_million", "nan"))
        ),
        selected_absolute_error_krw_million=float(
            str(body.get("selected_absolute_error_krw_million", "nan"))
        ),
        benchmark_absolute_error_krw_million=float(
            str(body.get("benchmark_absolute_error_krw_million", "nan"))
        ),
        absolute_error_advantage_krw_million=float(
            str(body.get("absolute_error_advantage_krw_million", "nan"))
        ),
        winner=str(body.get("winner", "")),
        status=str(body.get("status", "")),
        q3_target_read=body.get("q3_target_read") is True,
        q3_source_outcome_loaded=body.get("q3_source_outcome_loaded") is True,
        q3_evaluated=body.get("q3_evaluated") is True,
        model_refit_run=body.get("model_refit_run") is True,
        forecast_changed_after_lock=body.get("forecast_changed_after_lock") is True,
    )
    if _sha(_score_payload(item)) != item.evidence_id:
        raise ValueError("2026Q3 outcome score evidence mismatch")
    return item


def collect_2026q3_outcome_payload(
    client: OpenDartReadOnlyClient,
    contract: OutcomeScoringContract,
) -> object:
    corp = client.resolve_stock_codes([contract.ticker])[contract.ticker]
    batch = client.financial_statements(
        corp,
        business_year=contract.business_year,
        report_code=contract.report_code,
        fs_div=contract.fs_div,
    )
    if batch.corp.stock_code != contract.ticker:
        raise ValueError("2026Q3 outcome OpenDART batch ticker drifted")
    return batch.raw_payload


def score_locked_2026q3_forecast(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    contract_path: str | Path = DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT,
    output: str | Path = DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT,
) -> tuple[ProspectiveOutcomeScore, OutcomeSourceCapture, bool, bool]:
    contract = load_outcome_scoring_contract(contract_path)
    forecast = load_locked_numeric_forecast(contract.numeric_forecast_path)
    repair = load_frozen_historical_schema_repair_v2(contract.historical_execution_v2_path)
    execution = repair.runtime_execution
    if forecast.target_period != contract.target_period:
        raise ValueError("2026Q3 outcome scoring forecast period drifted")
    if forecast.q3_target_read or forecast.q3_source_outcome_loaded or forecast.q3_evaluated:
        raise ValueError("2026Q3 outcome scoring input forecast is not outcome-blind")
    if evaluation_date < contract.minimum_evaluation_date:
        raise ValueError("2026Q3 outcome scoring is prohibited before 2026-09-30")

    root = Path(output)
    score_pointer = root / "latest_outcome_score.json"
    capture_pointer = root / "latest_outcome_source_capture.json"
    if score_pointer.is_file():
        score = load_outcome_score(score_pointer)
        capture, _raw = load_outcome_source_capture(capture_pointer)
        if score.contract_evidence_id != contract.evidence_id:
            raise ValueError("Existing 2026Q3 outcome score belongs to another contract")
        if score.forecast_evidence_id != forecast.evidence_id:
            raise ValueError("Existing 2026Q3 outcome score forecast binding drifted")
        return score, capture, True, True

    capture_reused = capture_pointer.is_file()
    if capture_reused:
        capture, raw_payload = load_outcome_source_capture(capture_pointer)
        if capture.contract_evidence_id != contract.evidence_id:
            raise ValueError("Existing 2026Q3 outcome source belongs to another contract")
        if capture.forecast_evidence_id != forecast.evidence_id:
            raise ValueError("Existing 2026Q3 outcome source forecast binding drifted")
        if evaluation_date < capture.evaluation_date:
            raise ValueError("2026Q3 outcome replay evaluation date precedes locked capture date")
    else:
        raw_payload = collect_2026q3_outcome_payload(client, contract)
        if not _financial_rows(raw_payload):
            raise ValueError("2026Q3 official outcome is not available; nothing was persisted")
        capture = build_outcome_source_capture(
            contract,
            forecast,
            execution,
            evaluation_date=evaluation_date,
            raw_payload=raw_payload,
        )
        persist_outcome_source_capture(capture, raw_payload, output=root)

    observation = extract_outcome_observation(contract, execution, capture, raw_payload)
    score = build_outcome_score(contract, forecast, capture, observation)
    persist_outcome_score(score, output=root)
    return score, capture, capture_reused, False


__all__ = [
    "DEFAULT_2026Q3_OUTCOME_SCORE",
    "DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT",
    "DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT",
    "DEFAULT_2026Q3_OUTCOME_SOURCE_CAPTURE",
    "OutcomeObservation",
    "OutcomeScoringContract",
    "OutcomeSourceCapture",
    "ProspectiveOutcomeScore",
    "build_outcome_score",
    "build_outcome_source_capture",
    "collect_2026q3_outcome_payload",
    "extract_outcome_observation",
    "load_outcome_score",
    "load_outcome_scoring_contract",
    "load_outcome_source_capture",
    "persist_outcome_score",
    "persist_outcome_source_capture",
    "score_locked_2026q3_forecast",
]
