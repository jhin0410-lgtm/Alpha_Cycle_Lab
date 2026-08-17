"""Registry and audit for pre-2023 SK hynix profitability training-row candidates.

Candidate registration is not evidence promotion.  This module only records official
issuer-release provenance and the exact OpenDART acquisition coordinates that should be
attempted next.  A candidate remains unusable for training until product revenue, company
profitability, and four-field cycle-driver evidence are independently certified and then
reconciled by the structural pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import yaml

DEFAULT_HISTORICAL_EXPANSION_FRONTIER = Path(
    "config/skhynix_product_profitability_historical_expansion_frontier.v1.yaml"
)
_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_ALLOWED_CAPTURE_STATUS = frozenset({"not_attempted", "captured", "certified", "failed"})
_ALLOWED_DRIVER_STATUS = frozenset({"not_certified", "certified", "failed"})
_ALLOWED_ROW_STATUS = frozenset({"not_certified", "certified", "failed"})


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


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Historical expansion {label} must be an object")
    return cast(dict[object, object], value)


def _date(value: object, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Historical expansion {label} must be ISO date") from exc


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Historical expansion {label} must be boolean")
    return value


@dataclass(frozen=True)
class HistoricalExpansionCandidate:
    period_id: str
    period_start: date
    period_end: date
    issuer_release_url: str
    issuer_release_published_date: date
    issuer_release_verified_present: bool
    opendart_report_name_exact: str
    opendart_discovery_begin_date: date
    opendart_discovery_end_date: date
    company_profitability_report_code: str
    product_parser_compatibility_status: str
    opendart_product_revenue_capture_status: str
    opendart_company_profitability_capture_status: str
    cycle_driver_four_field_source_status: str
    training_row_status: str

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical expansion candidate period is unsupported")
        year = int(self.period_id[:4])
        quarter = int(self.period_id[-1])
        expected_start_month = 1 + (quarter - 1) * 3
        expected_end_month = quarter * 3
        expected_end_day = 31 if expected_end_month in {3, 12} else 30
        if self.period_start != date(year, expected_start_month, 1):
            raise ValueError("Historical expansion candidate start date is inconsistent")
        if self.period_end != date(year, expected_end_month, expected_end_day):
            raise ValueError("Historical expansion candidate end date is inconsistent")
        parsed = urlparse(self.issuer_release_url)
        if parsed.scheme != "https" or parsed.netloc != "news.skhynix.com":
            raise ValueError("Historical expansion issuer release must use official SK hynix Newsroom")
        if not self.issuer_release_verified_present:
            raise ValueError("Historical expansion candidate requires verified issuer-release presence")
        if self.issuer_release_published_date <= self.period_end:
            raise ValueError("Historical expansion release date cannot precede quarter end")
        expected_report = {
            1: f"분기보고서 ({year}.03)",
            2: f"반기보고서 ({year}.06)",
            3: f"분기보고서 ({year}.09)",
        }[quarter]
        if self.opendart_report_name_exact != expected_report:
            raise ValueError("Historical expansion OpenDART report name is inconsistent")
        if self.opendart_discovery_begin_date > self.opendart_discovery_end_date:
            raise ValueError("Historical expansion discovery window is invalid")
        expected_code = {1: "11013", 2: "11012", 3: "11014"}[quarter]
        if self.company_profitability_report_code != expected_code:
            raise ValueError("Historical expansion company report code is inconsistent")
        if self.product_parser_compatibility_status != "untested_historical_layout":
            raise ValueError("Historical expansion parser compatibility cannot be pre-certified")
        if self.opendart_product_revenue_capture_status not in _ALLOWED_CAPTURE_STATUS:
            raise ValueError("Historical expansion product-revenue status is invalid")
        if self.opendart_company_profitability_capture_status not in _ALLOWED_CAPTURE_STATUS:
            raise ValueError("Historical expansion company-profitability status is invalid")
        if self.cycle_driver_four_field_source_status not in _ALLOWED_DRIVER_STATUS:
            raise ValueError("Historical expansion cycle-driver status is invalid")
        if self.training_row_status not in _ALLOWED_ROW_STATUS:
            raise ValueError("Historical expansion training-row status is invalid")
        source_layers_certified = (
            self.opendart_product_revenue_capture_status == "certified"
            and self.opendart_company_profitability_capture_status == "certified"
            and self.cycle_driver_four_field_source_status == "certified"
        )
        if self.training_row_status == "certified" and not source_layers_certified:
            raise ValueError("Historical expansion row cannot be certified before all source layers")

    @property
    def source_layers_certified(self) -> bool:
        return (
            self.opendart_product_revenue_capture_status == "certified"
            and self.opendart_company_profitability_capture_status == "certified"
            and self.cycle_driver_four_field_source_status == "certified"
        )


@dataclass(frozen=True)
class HistoricalExpansionFrontier:
    evidence_id: str
    frontier_id: str
    frontier_version: str
    ticker: str
    purpose: str
    target_additional_training_rows: int
    holdout_period: str
    q4_direct_quarter_derivation_allowed: bool
    candidates: tuple[HistoricalExpansionCandidate, ...]
    issuer_release_presence_is_training_row_evidence: bool
    newsroom_release_is_product_revenue_certification: bool
    qualitative_commentary_is_four_field_cycle_driver_certification: bool
    candidate_registration_enables_fit: bool
    candidate_registration_enables_holdout: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.frontier_id != "skhynix_product_profitability_historical_expansion":
            raise ValueError("Historical expansion frontier id is unsupported")
        if self.frontier_version != "0.1-draft" or self.ticker != "000660":
            raise ValueError("Historical expansion frontier identity drifted")
        if self.purpose != "training_sample_expansion_only":
            raise ValueError("Historical expansion frontier purpose is invalid")
        if self.target_additional_training_rows != len(_EXPECTED_PERIODS):
            raise ValueError("Historical expansion target must remain six rows")
        if self.holdout_period != "2026Q1" or self.q4_direct_quarter_derivation_allowed:
            raise ValueError("Historical expansion holdout/Q4 boundary drifted")
        if tuple(item.period_id for item in self.candidates) != _EXPECTED_PERIODS:
            raise ValueError("Historical expansion candidates must bind exact six periods")
        forbidden = (
            self.issuer_release_presence_is_training_row_evidence,
            self.newsroom_release_is_product_revenue_certification,
            self.qualitative_commentary_is_four_field_cycle_driver_certification,
            self.candidate_registration_enables_fit,
            self.candidate_registration_enables_holdout,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Historical expansion frontier exceeded its trust boundary")
        if len(self.evidence_id) != 64:
            raise ValueError("Historical expansion frontier evidence id must be SHA-256")


@dataclass(frozen=True)
class HistoricalExpansionAudit:
    frontier_evidence_id: str
    candidate_count: int
    target_additional_training_rows: int
    issuer_release_verified_count: int
    product_revenue_certified_count: int
    company_profitability_certified_count: int
    cycle_driver_certified_count: int
    source_layer_complete_count: int
    training_row_certified_count: int
    remaining_candidate_rows: int
    fit_enabled: bool = False
    holdout_evaluation_enabled: bool = False

    def __post_init__(self) -> None:
        if self.candidate_count != self.target_additional_training_rows:
            raise ValueError("Historical expansion candidate target/count mismatch")
        counts = (
            self.issuer_release_verified_count,
            self.product_revenue_certified_count,
            self.company_profitability_certified_count,
            self.cycle_driver_certified_count,
            self.source_layer_complete_count,
            self.training_row_certified_count,
        )
        if any(value < 0 or value > self.candidate_count for value in counts):
            raise ValueError("Historical expansion audit count is invalid")
        if self.remaining_candidate_rows != self.candidate_count - self.training_row_certified_count:
            raise ValueError("Historical expansion remaining-row count is inconsistent")
        if self.fit_enabled or self.holdout_evaluation_enabled:
            raise ValueError("Historical expansion audit cannot open fit/holdout")


def load_historical_expansion_frontier(
    path: str | Path = DEFAULT_HISTORICAL_EXPANSION_FRONTIER,
) -> HistoricalExpansionFrontier:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Historical expansion manifest schema is invalid")
    frontier = _mapping(root.get("frontier"), "frontier")
    raw_candidates = frontier.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("Historical expansion candidates must be an array")
    candidates: list[HistoricalExpansionCandidate] = []
    for raw_candidate in raw_candidates:
        item = _mapping(raw_candidate, "candidate")
        candidates.append(
            HistoricalExpansionCandidate(
                period_id=str(item.get("period_id", "")),
                period_start=_date(item.get("period_start"), "period_start"),
                period_end=_date(item.get("period_end"), "period_end"),
                issuer_release_url=str(item.get("issuer_release_url", "")),
                issuer_release_published_date=_date(
                    item.get("issuer_release_published_date"), "issuer_release_published_date"
                ),
                issuer_release_verified_present=_strict_bool(
                    item.get("issuer_release_verified_present"),
                    "issuer_release_verified_present",
                ),
                opendart_report_name_exact=str(item.get("opendart_report_name_exact", "")),
                opendart_discovery_begin_date=_date(
                    item.get("opendart_discovery_begin_date"), "opendart_discovery_begin_date"
                ),
                opendart_discovery_end_date=_date(
                    item.get("opendart_discovery_end_date"), "opendart_discovery_end_date"
                ),
                company_profitability_report_code=str(
                    item.get("company_profitability_report_code", "")
                ),
                product_parser_compatibility_status=str(
                    item.get("product_parser_compatibility_status", "")
                ),
                opendart_product_revenue_capture_status=str(
                    item.get("opendart_product_revenue_capture_status", "")
                ),
                opendart_company_profitability_capture_status=str(
                    item.get("opendart_company_profitability_capture_status", "")
                ),
                cycle_driver_four_field_source_status=str(
                    item.get("cycle_driver_four_field_source_status", "")
                ),
                training_row_status=str(item.get("training_row_status", "")),
            )
        )
    trust = _mapping(frontier.get("trust_boundary"), "trust_boundary")
    stable = {
        "frontier_id": frontier.get("frontier_id"),
        "frontier_version": frontier.get("frontier_version"),
        "ticker": frontier.get("ticker"),
        "purpose": frontier.get("purpose"),
        "target_additional_training_rows": frontier.get("target_additional_training_rows"),
        "holdout_period": frontier.get("holdout_period"),
        "q4_direct_quarter_derivation_allowed": frontier.get(
            "q4_direct_quarter_derivation_allowed"
        ),
        "candidates": [asdict(item) for item in candidates],
        "trust_boundary": trust,
    }
    return HistoricalExpansionFrontier(
        evidence_id=_sha_payload(stable),
        frontier_id=str(frontier.get("frontier_id", "")),
        frontier_version=str(frontier.get("frontier_version", "")),
        ticker=str(frontier.get("ticker", "")).zfill(6),
        purpose=str(frontier.get("purpose", "")),
        target_additional_training_rows=int(str(frontier.get("target_additional_training_rows", 0))),
        holdout_period=str(frontier.get("holdout_period", "")),
        q4_direct_quarter_derivation_allowed=_strict_bool(
            frontier.get("q4_direct_quarter_derivation_allowed"),
            "q4_direct_quarter_derivation_allowed",
        ),
        candidates=tuple(candidates),
        issuer_release_presence_is_training_row_evidence=_strict_bool(
            trust.get("issuer_release_presence_is_training_row_evidence"),
            "issuer_release_presence_is_training_row_evidence",
        ),
        newsroom_release_is_product_revenue_certification=_strict_bool(
            trust.get("newsroom_release_is_product_revenue_certification"),
            "newsroom_release_is_product_revenue_certification",
        ),
        qualitative_commentary_is_four_field_cycle_driver_certification=_strict_bool(
            trust.get("qualitative_commentary_is_four_field_cycle_driver_certification"),
            "qualitative_commentary_is_four_field_cycle_driver_certification",
        ),
        candidate_registration_enables_fit=_strict_bool(
            trust.get("candidate_registration_enables_fit"),
            "candidate_registration_enables_fit",
        ),
        candidate_registration_enables_holdout=_strict_bool(
            trust.get("candidate_registration_enables_holdout"),
            "candidate_registration_enables_holdout",
        ),
        numeric_forecast_enabled=_strict_bool(
            trust.get("numeric_forecast_enabled"), "numeric_forecast_enabled"
        ),
        fair_value_estimate_enabled=_strict_bool(
            trust.get("fair_value_estimate_enabled"), "fair_value_estimate_enabled"
        ),
        target_price_enabled=_strict_bool(
            trust.get("target_price_enabled"), "target_price_enabled"
        ),
        decision_score_enabled=_strict_bool(
            trust.get("decision_score_enabled"), "decision_score_enabled"
        ),
    )


def audit_historical_expansion_frontier(
    frontier: HistoricalExpansionFrontier,
) -> HistoricalExpansionAudit:
    candidates = frontier.candidates
    return HistoricalExpansionAudit(
        frontier_evidence_id=frontier.evidence_id,
        candidate_count=len(candidates),
        target_additional_training_rows=frontier.target_additional_training_rows,
        issuer_release_verified_count=sum(item.issuer_release_verified_present for item in candidates),
        product_revenue_certified_count=sum(
            item.opendart_product_revenue_capture_status == "certified" for item in candidates
        ),
        company_profitability_certified_count=sum(
            item.opendart_company_profitability_capture_status == "certified" for item in candidates
        ),
        cycle_driver_certified_count=sum(
            item.cycle_driver_four_field_source_status == "certified" for item in candidates
        ),
        source_layer_complete_count=sum(item.source_layers_certified for item in candidates),
        training_row_certified_count=sum(
            item.training_row_status == "certified" for item in candidates
        ),
        remaining_candidate_rows=sum(
            item.training_row_status != "certified" for item in candidates
        ),
    )


__all__ = [
    "DEFAULT_HISTORICAL_EXPANSION_FRONTIER",
    "HistoricalExpansionAudit",
    "HistoricalExpansionCandidate",
    "HistoricalExpansionFrontier",
    "audit_historical_expansion_frontier",
    "load_historical_expansion_frontier",
]
