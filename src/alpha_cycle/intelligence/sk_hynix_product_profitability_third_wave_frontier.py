"""Validated 2017Q1-2018Q3 exact-numeric SK hynix v2 identification frontier.

The six issuer releases expose all four DRAM/NAND QoQ shipment/ASP drivers numerically.
Product revenue and consolidated profitability remain separate OpenDART source layers. The
frontier exists after the v1 2026Q1 holdout was spent, so it cannot refit v1 and cannot reuse
2026Q1 as an unseen v2 holdout.
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

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveDrivers,
)

DEFAULT_THIRD_WAVE_FRONTIER = Path(
    "config/skhynix_product_profitability_third_wave_frontier.v1.yaml"
)
_EXPECTED_PERIODS = (
    "2017Q1",
    "2017Q2",
    "2017Q3",
    "2018Q1",
    "2018Q2",
    "2018Q3",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Third-wave frontier {label} must be an object")
    return cast(dict[object, object], value)


def _date(value: object, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Third-wave frontier {label} must be ISO date") from exc


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ThirdWaveCandidate:
    period_id: str
    period_start: date
    period_end: date
    issuer_release_url: str
    issuer_release_published_date: date
    opendart_report_name_exact: str
    opendart_discovery_begin_date: date
    opendart_discovery_end_date: date
    company_profitability_report_code: str
    drivers_qoq_percent: SecondWaveDrivers

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Third-wave candidate period is unsupported")
        year = int(self.period_id[:4])
        quarter = int(self.period_id[-1])
        if quarter not in {1, 2, 3}:
            raise ValueError("Third-wave frontier forbids Q4")
        start_month = 1 + (quarter - 1) * 3
        end_month = quarter * 3
        end_day = 31 if end_month == 3 else 30
        if self.period_start != date(year, start_month, 1):
            raise ValueError("Third-wave candidate start date is inconsistent")
        if self.period_end != date(year, end_month, end_day):
            raise ValueError("Third-wave candidate end date is inconsistent")
        parsed = urlparse(self.issuer_release_url)
        if parsed.scheme != "https" or parsed.netloc != "news.skhynix.com":
            raise ValueError("Third-wave driver source must be official SK hynix Newsroom")
        if self.issuer_release_published_date <= self.period_end:
            raise ValueError("Third-wave release cannot precede quarter end")
        expected_report = {
            1: f"분기보고서 ({year}.03)",
            2: f"반기보고서 ({year}.06)",
            3: f"분기보고서 ({year}.09)",
        }[quarter]
        if self.opendart_report_name_exact != expected_report:
            raise ValueError("Third-wave OpenDART report name is inconsistent")
        expected_code = {1: "11013", 2: "11012", 3: "11014"}[quarter]
        if self.company_profitability_report_code != expected_code:
            raise ValueError("Third-wave company report code is inconsistent")
        if self.opendart_discovery_begin_date > self.opendart_discovery_end_date:
            raise ValueError("Third-wave OpenDART discovery window is invalid")


@dataclass(frozen=True)
class ThirdWaveFrontier:
    evidence_id: str
    frontier_id: str
    frontier_version: str
    ticker: str
    purpose: str
    target_additional_training_rows: int
    spent_v1_holdout_period: str
    q4_direct_quarter_derivation_allowed: bool
    candidates: tuple[ThirdWaveCandidate, ...]
    issuer_driver_values_are_exact_numeric_source_facts: bool
    product_revenue_certified: bool
    company_profitability_certified: bool
    training_row_promoted: bool
    v1_refit_enabled: bool
    v2_fit_enabled: bool
    reuse_2026q1_as_unseen_holdout_for_v2_allowed: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.frontier_id != "skhynix_product_profitability_third_wave":
            raise ValueError("Third-wave frontier id is unsupported")
        if self.frontier_version != "0.1-draft" or self.ticker != "000660":
            raise ValueError("Third-wave frontier identity drifted")
        if self.purpose != "exact_six_row_identification_expansion_after_v1_holdout":
            raise ValueError("Third-wave frontier purpose drifted")
        if self.target_additional_training_rows != 6:
            raise ValueError("Third-wave frontier target must remain six rows")
        if self.spent_v1_holdout_period != "2026Q1":
            raise ValueError("Third-wave frontier spent holdout binding drifted")
        if self.q4_direct_quarter_derivation_allowed:
            raise ValueError("Third-wave frontier cannot derive direct Q4 rows")
        if tuple(item.period_id for item in self.candidates) != _EXPECTED_PERIODS:
            raise ValueError("Third-wave frontier periods are incomplete")
        if not self.issuer_driver_values_are_exact_numeric_source_facts:
            raise ValueError("Third-wave drivers must remain exact issuer source facts")
        forbidden = (
            self.product_revenue_certified,
            self.company_profitability_certified,
            self.training_row_promoted,
            self.v1_refit_enabled,
            self.v2_fit_enabled,
            self.reuse_2026q1_as_unseen_holdout_for_v2_allowed,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Third-wave frontier exceeded pre-acquisition trust boundary")
        if len(self.evidence_id) != 64:
            raise ValueError("Third-wave frontier evidence id must be SHA-256")


def _candidate(item: dict[object, object]) -> ThirdWaveCandidate:
    drivers = _mapping(item.get("drivers_qoq_percent"), "drivers")
    return ThirdWaveCandidate(
        period_id=str(item.get("period_id", "")),
        period_start=_date(item.get("period_start"), "period_start"),
        period_end=_date(item.get("period_end"), "period_end"),
        issuer_release_url=str(item.get("issuer_release_url", "")),
        issuer_release_published_date=_date(
            item.get("issuer_release_published_date"), "issuer_release_published_date"
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
        drivers_qoq_percent=SecondWaveDrivers(
            dram_bit_volume=float(str(drivers.get("dram_bit_volume"))),
            dram_asp=float(str(drivers.get("dram_asp"))),
            nand_bit_volume=float(str(drivers.get("nand_bit_volume"))),
            nand_asp=float(str(drivers.get("nand_asp"))),
        ),
    )


def load_third_wave_frontier(
    path: str | Path = DEFAULT_THIRD_WAVE_FRONTIER,
) -> ThirdWaveFrontier:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Third-wave frontier schema is invalid")
    frontier = _mapping(root.get("frontier"), "frontier")
    raw_candidates = frontier.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("Third-wave candidates must be an array")
    candidates = tuple(_candidate(_mapping(item, "candidate")) for item in raw_candidates)
    trust = _mapping(frontier.get("trust_boundary"), "trust_boundary")
    stable = {
        "frontier_id": frontier.get("frontier_id"),
        "frontier_version": frontier.get("frontier_version"),
        "ticker": frontier.get("ticker"),
        "purpose": frontier.get("purpose"),
        "target": frontier.get("target_additional_training_rows"),
        "spent_v1_holdout_period": frontier.get("spent_v1_holdout_period"),
        "q4": frontier.get("q4_direct_quarter_derivation_allowed"),
        "candidates": [asdict(item) for item in candidates],
        "trust_boundary": trust,
    }
    return ThirdWaveFrontier(
        evidence_id=_sha(stable),
        frontier_id=str(frontier.get("frontier_id", "")),
        frontier_version=str(frontier.get("frontier_version", "")),
        ticker=str(frontier.get("ticker", "")).zfill(6),
        purpose=str(frontier.get("purpose", "")),
        target_additional_training_rows=int(
            str(frontier.get("target_additional_training_rows", 0))
        ),
        spent_v1_holdout_period=str(frontier.get("spent_v1_holdout_period", "")),
        q4_direct_quarter_derivation_allowed=(
            frontier.get("q4_direct_quarter_derivation_allowed") is True
        ),
        candidates=candidates,
        issuer_driver_values_are_exact_numeric_source_facts=(
            trust.get("issuer_driver_values_are_exact_numeric_source_facts") is True
        ),
        product_revenue_certified=trust.get("product_revenue_certified") is True,
        company_profitability_certified=trust.get("company_profitability_certified") is True,
        training_row_promoted=trust.get("training_row_promoted") is True,
        v1_refit_enabled=trust.get("v1_refit_enabled") is True,
        v2_fit_enabled=trust.get("v2_fit_enabled") is True,
        reuse_2026q1_as_unseen_holdout_for_v2_allowed=(
            trust.get("reuse_2026q1_as_unseen_holdout_for_v2_allowed") is True
        ),
        numeric_forecast_enabled=trust.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_THIRD_WAVE_FRONTIER",
    "ThirdWaveCandidate",
    "ThirdWaveFrontier",
    "load_third_wave_frontier",
]
