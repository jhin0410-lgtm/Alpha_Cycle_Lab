"""Load the frozen SK hynix company-GP ex-ante forecast protocol.

The protocol is intentionally target-blind at the feature-build stage. It defines a
calendar-based forecast origin, chronological evaluation, and protected future outcomes
without reading 2026Q3 or 2026Q4 target values.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout_protocol import (
    DEFAULT_V5_Q3_HOLDOUT_PROTOCOL,
    load_frozen_v5_q3_holdout_protocol,
)
from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
    load_frozen_company_gp_empirical_method,
)

DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL = Path(
    "config/skhynix_company_gp_ex_ante_forecast_protocol.v1.yaml"
)
_EXPECTED_DEVELOPMENT_PERIODS = (
    "2017Q1",
    "2017Q2",
    "2017Q3",
    "2018Q1",
    "2018Q2",
    "2018Q3",
    "2019Q1",
    "2019Q2",
    "2019Q3",
    "2020Q1",
    "2020Q2",
    "2020Q3",
    "2023Q1",
    "2023Q2",
    "2023Q3",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2025Q1",
    "2025Q2",
    "2025Q3",
)
_KOREA_TZ = ZoneInfo("Asia/Seoul")


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Ex-ante protocol {label} must be an object")
    return cast(dict[object, object], value)


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


def _bool(mapping: dict[object, object], key: str) -> bool:
    return mapping.get(key) is True


def quarter_end(period_id: str) -> date:
    """Return the calendar quarter-end date for a YYYYQn period id."""

    if len(period_id) != 6 or period_id[4] != "Q" or period_id[5] not in "1234":
        raise ValueError(f"Invalid quarter period id: {period_id}")
    year_text = period_id[:4]
    if not year_text.isdigit():
        raise ValueError(f"Invalid quarter period year: {period_id}")
    year = int(year_text)
    quarter = int(period_id[5])
    month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
    return date(year, month_day[0], month_day[1])


@dataclass(frozen=True)
class ExAnteForecastOrigin:
    rule: str
    cutoff_time_local: time
    timezone: str

    def __post_init__(self) -> None:
        if self.rule != "quarter_end_minus_30_calendar_days":
            raise ValueError("Ex-ante forecast origin rule drifted")
        if self.cutoff_time_local != time(23, 59, 59):
            raise ValueError("Ex-ante cutoff time drifted")
        if self.timezone != "Asia/Seoul":
            raise ValueError("Ex-ante forecast timezone drifted")

    def for_period(self, period_id: str) -> datetime:
        cutoff_date = quarter_end(period_id) - timedelta(days=30)
        return datetime.combine(cutoff_date, self.cutoff_time_local, tzinfo=_KOREA_TZ)


@dataclass(frozen=True)
class ExAnteHistoricalEvaluation:
    scheme: str
    random_cross_validation_allowed: bool
    primary_metric: str
    benchmark_id: str
    candidate_must_strictly_beat_benchmark: bool
    minimum_scored_folds: int
    minimum_training_rows_per_fold: int

    def __post_init__(self) -> None:
        if self.scheme != "chronological_expanding_window":
            raise ValueError("Ex-ante historical evaluation scheme drifted")
        if self.random_cross_validation_allowed:
            raise ValueError("Ex-ante evaluation cannot use random cross-validation")
        if self.primary_metric != "mae_krw_million":
            raise ValueError("Ex-ante primary metric drifted")
        if self.benchmark_id != "previous_reported_quarter_gross_profit_persistence":
            raise ValueError("Ex-ante benchmark drifted")
        if not self.candidate_must_strictly_beat_benchmark:
            raise ValueError("Ex-ante candidate must strictly beat benchmark")
        if self.minimum_scored_folds != 8 or self.minimum_training_rows_per_fold != 6:
            raise ValueError("Ex-ante chronological fold floor drifted")


@dataclass(frozen=True)
class FrozenCompanyGPExAnteProtocol:
    evidence_id: str
    protocol_id: str
    protocol_version: str
    status: str
    ticker: str
    target_metric: str
    scientific_scope: str
    bound_v5_method_evidence_id: str
    bound_v5_q3_protocol_evidence_id: str
    forecast_origin: ExAnteForecastOrigin
    development_periods: tuple[str, ...]
    contaminated_report_only_periods: tuple[str, ...]
    historical_evaluation: ExAnteHistoricalEvaluation
    minimum_complete_development_rows_for_any_model: int
    estimator_frozen: bool
    final_feature_set_frozen: bool
    separate_estimator_freeze_required: bool
    q3_role: str
    q3_fallback_period: str
    q3_target_read: bool
    q3_source_outcome_loaded: bool
    q3_evaluated: bool
    q4_target_read: bool
    numeric_forward_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    investment_action_enabled: bool

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.bound_v5_method_evidence_id,
            self.bound_v5_q3_protocol_evidence_id,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("Ex-ante protocol evidence ids must be SHA-256")
        if self.protocol_id != "skhynix_company_gp_ex_ante_quarterly_forecast":
            raise ValueError("Ex-ante protocol id drifted")
        if (
            self.protocol_version != "1.0-frozen-pre-pit-backtest"
            or self.status != "frozen_pre_pit_backtest"
        ):
            raise ValueError("Ex-ante protocol is not frozen pre-PIT-backtest")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Ex-ante ticker or target drifted")
        if self.scientific_scope != "pre_earnings_company_gp_forecast":
            raise ValueError("Ex-ante scientific scope drifted")
        if self.development_periods != _EXPECTED_DEVELOPMENT_PERIODS:
            raise ValueError("Ex-ante development periods drifted")
        if self.contaminated_report_only_periods != ("2026Q1",):
            raise ValueError("Ex-ante contaminated period contract drifted")
        if self.minimum_complete_development_rows_for_any_model != 12:
            raise ValueError("Ex-ante minimum row heuristic drifted")
        if self.estimator_frozen or self.final_feature_set_frozen:
            raise ValueError("Ex-ante estimator or final feature set was frozen too early")
        if not self.separate_estimator_freeze_required:
            raise ValueError("Ex-ante estimator requires a separate future freeze")
        if self.q3_role != "co_protected_prospective_candidate":
            raise ValueError("Ex-ante 2026Q3 protected role drifted")
        if self.q3_fallback_period != "2026Q4":
            raise ValueError("Ex-ante 2026Q3 fallback period drifted")
        if any(
            (
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.q3_evaluated,
                self.q4_target_read,
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
                self.investment_action_enabled,
            )
        ):
            raise ValueError("Ex-ante protocol opened protected future or investment outputs")

    def origin_for(self, period_id: str) -> datetime:
        return self.forecast_origin.for_period(period_id)


def load_frozen_company_gp_ex_ante_protocol(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    *,
    v5_method_path: str | Path = DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
    v5_q3_protocol_path: str | Path = DEFAULT_V5_Q3_HOLDOUT_PROTOCOL,
) -> FrozenCompanyGPExAnteProtocol:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Ex-ante protocol schema is invalid")
    body = _mapping(root.get("protocol"), "body")
    origin = _mapping(body.get("forecast_origin"), "forecast_origin")
    evaluation = _mapping(body.get("historical_evaluation"), "historical_evaluation")
    development = body.get("development_periods")
    contaminated = body.get("contaminated_report_only_periods")
    if not isinstance(development, list) or not isinstance(contaminated, list):
        raise ValueError("Ex-ante protocol period lists are invalid")
    protected = _mapping(body.get("protected_future_outcomes"), "protected_future_outcomes")
    q3 = _mapping(protected.get("2026Q3"), "protected_future_outcomes.2026Q3")
    readiness = _mapping(body.get("readiness_gate"), "readiness_gate")
    model = _mapping(body.get("model_development"), "model_development")
    trust = _mapping(body.get("trust_boundary"), "trust_boundary")

    v5 = load_frozen_company_gp_empirical_method(v5_method_path)
    q3_protocol, q3_method = load_frozen_v5_q3_holdout_protocol(
        v5_q3_protocol_path,
        method_path=v5_method_path,
    )
    bound_method = str(body.get("bound_v5_method_evidence_id", ""))
    bound_q3 = str(body.get("bound_v5_q3_protocol_evidence_id", ""))
    if bound_method != v5.evidence_id or q3_method.evidence_id != v5.evidence_id:
        raise ValueError("Ex-ante protocol does not bind the current frozen V5 method")
    if bound_q3 != q3_protocol.evidence_id:
        raise ValueError("Ex-ante protocol does not bind the current frozen V5 Q3 protocol")

    cutoff_text = str(origin.get("cutoff_time_local", ""))
    try:
        cutoff_time = time.fromisoformat(cutoff_text)
    except ValueError as exc:
        raise ValueError("Ex-ante cutoff_time_local is invalid") from exc

    stable = {"schema_version": root["schema_version"], "protocol": body}
    return FrozenCompanyGPExAnteProtocol(
        evidence_id=_sha(stable),
        protocol_id=str(body.get("protocol_id", "")),
        protocol_version=str(body.get("protocol_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        scientific_scope=str(body.get("scientific_scope", "")),
        bound_v5_method_evidence_id=bound_method,
        bound_v5_q3_protocol_evidence_id=bound_q3,
        forecast_origin=ExAnteForecastOrigin(
            rule=str(origin.get("rule", "")),
            cutoff_time_local=cutoff_time,
            timezone=str(origin.get("timezone", "")),
        ),
        development_periods=tuple(str(item) for item in development),
        contaminated_report_only_periods=tuple(str(item) for item in contaminated),
        historical_evaluation=ExAnteHistoricalEvaluation(
            scheme=str(evaluation.get("scheme", "")),
            random_cross_validation_allowed=_bool(
                evaluation,
                "random_cross_validation_allowed",
            ),
            primary_metric=str(evaluation.get("primary_metric", "")),
            benchmark_id=str(evaluation.get("benchmark_id", "")),
            candidate_must_strictly_beat_benchmark=_bool(
                evaluation,
                "candidate_must_strictly_beat_benchmark",
            ),
            minimum_scored_folds=int(str(evaluation.get("minimum_scored_folds", -1))),
            minimum_training_rows_per_fold=int(
                str(evaluation.get("minimum_training_rows_per_fold", -1))
            ),
        ),
        minimum_complete_development_rows_for_any_model=int(
            str(readiness.get("minimum_complete_development_rows_for_any_model", -1))
        ),
        estimator_frozen=_bool(model, "estimator_frozen_in_this_protocol"),
        final_feature_set_frozen=_bool(model, "final_feature_set_frozen_in_this_protocol"),
        separate_estimator_freeze_required=_bool(
            model,
            "separate_estimator_freeze_required_before_prospective_forecast",
        ),
        q3_role=str(q3.get("role", "")),
        q3_fallback_period=str(q3.get("fallback_if_origin_missed", "")),
        q3_target_read=_bool(trust, "2026q3_target_read"),
        q3_source_outcome_loaded=_bool(trust, "2026q3_source_outcome_loaded"),
        q3_evaluated=_bool(trust, "2026q3_evaluated"),
        q4_target_read=_bool(trust, "2026q4_target_read"),
        numeric_forward_forecast_enabled=_bool(trust, "numeric_forward_forecast_enabled"),
        fair_value_estimate_enabled=_bool(trust, "fair_value_estimate_enabled"),
        target_price_enabled=_bool(trust, "target_price_enabled"),
        decision_score_enabled=_bool(trust, "decision_score_enabled"),
        investment_action_enabled=_bool(trust, "investment_action_enabled"),
    )


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL",
    "ExAnteForecastOrigin",
    "ExAnteHistoricalEvaluation",
    "FrozenCompanyGPExAnteProtocol",
    "load_frozen_company_gp_ex_ante_protocol",
    "quarter_end",
]
