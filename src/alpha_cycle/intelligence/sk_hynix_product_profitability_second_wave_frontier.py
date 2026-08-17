"""Validated 2019Q1-2020Q3 SK hynix six-row expansion frontier.

These periods are selected because the issuer Newsroom reports all four DRAM/NAND QoQ
shipment/ASP drivers numerically. Product revenue and company profitability remain separate
OpenDART source layers and must be certified before any training-row promotion.
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

DEFAULT_SECOND_WAVE_FRONTIER = Path(
    "config/skhynix_product_profitability_second_wave_frontier.v1.yaml"
)
_EXPECTED_PERIODS = (
    "2019Q1",
    "2019Q2",
    "2019Q3",
    "2020Q1",
    "2020Q2",
    "2020Q3",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Second-wave frontier {label} must be an object")
    return cast(dict[object, object], value)


def _date(value: object, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Second-wave frontier {label} must be ISO date") from exc


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


@dataclass(frozen=True)
class SecondWaveDrivers:
    dram_bit_volume: float
    dram_asp: float
    nand_bit_volume: float
    nand_asp: float

    def __post_init__(self) -> None:
        values = (
            self.dram_bit_volume,
            self.dram_asp,
            self.nand_bit_volume,
            self.nand_asp,
        )
        if any(not -100.0 <= value <= 100.0 for value in values):
            raise ValueError("Second-wave driver value is outside the admitted QoQ range")


@dataclass(frozen=True)
class SecondWaveCandidate:
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
            raise ValueError("Second-wave candidate period is unsupported")
        year = int(self.period_id[:4])
        quarter = int(self.period_id[-1])
        if quarter not in {1, 2, 3}:
            raise ValueError("Second-wave frontier forbids Q4")
        start_month = 1 + (quarter - 1) * 3
        end_month = quarter * 3
        end_day = 31 if end_month == 3 else 30
        if self.period_start != date(year, start_month, 1):
            raise ValueError("Second-wave candidate start date is inconsistent")
        if self.period_end != date(year, end_month, end_day):
            raise ValueError("Second-wave candidate end date is inconsistent")
        parsed = urlparse(self.issuer_release_url)
        if parsed.scheme != "https" or parsed.netloc != "news.skhynix.com":
            raise ValueError("Second-wave driver source must be official SK hynix Newsroom")
        if self.issuer_release_published_date <= self.period_end:
            raise ValueError("Second-wave release cannot precede quarter end")
        expected_report = {
            1: f"분기보고서 ({year}.03)",
            2: f"반기보고서 ({year}.06)",
            3: f"분기보고서 ({year}.09)",
        }[quarter]
        if self.opendart_report_name_exact != expected_report:
            raise ValueError("Second-wave OpenDART report name is inconsistent")
        expected_code = {1: "11013", 2: "11012", 3: "11014"}[quarter]
        if self.company_profitability_report_code != expected_code:
            raise ValueError("Second-wave company report code is inconsistent")
        if self.opendart_discovery_begin_date > self.opendart_discovery_end_date:
            raise ValueError("Second-wave OpenDART discovery window is invalid")


@dataclass(frozen=True)
class SecondWaveFrontier:
    evidence_id: str
    frontier_id: str
    frontier_version: str
    ticker: str
    purpose: str
    target_additional_training_rows: int
    holdout_period: str
    q4_direct_quarter_derivation_allowed: bool
    candidates: tuple[SecondWaveCandidate, ...]
    issuer_driver_values_are_exact_numeric_source_facts: bool
    product_revenue_certified: bool
    company_profitability_certified: bool
    training_row_promoted: bool
    candidate_registration_enables_fit: bool
    candidate_registration_enables_holdout: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.frontier_id != "skhynix_product_profitability_second_wave":
            raise ValueError("Second-wave frontier id is unsupported")
        if self.frontier_version != "0.1-draft" or self.ticker != "000660":
            raise ValueError("Second-wave frontier identity drifted")
        if self.purpose != "exact_six_row_training_sample_expansion":
            raise ValueError("Second-wave frontier purpose is invalid")
        if self.target_additional_training_rows != 6:
            raise ValueError("Second-wave frontier target must remain six rows")
        if self.holdout_period != "2026Q1" or self.q4_direct_quarter_derivation_allowed:
            raise ValueError("Second-wave frontier holdout/Q4 boundary drifted")
        if tuple(item.period_id for item in self.candidates) != _EXPECTED_PERIODS:
            raise ValueError("Second-wave frontier periods are incomplete")
        if not self.issuer_driver_values_are_exact_numeric_source_facts:
            raise ValueError("Second-wave driver values must remain direct issuer source facts")
        forbidden = (
            self.product_revenue_certified,
            self.company_profitability_certified,
            self.training_row_promoted,
            self.candidate_registration_enables_fit,
            self.candidate_registration_enables_holdout,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Second-wave frontier exceeded pre-acquisition trust boundary")
        if len(self.evidence_id) != 64:
            raise ValueError("Second-wave frontier evidence id must be SHA-256")


def _candidate(item: dict[object, object]) -> SecondWaveCandidate:
    drivers = _mapping(item.get("drivers_qoq_percent"), "drivers")
    return SecondWaveCandidate(
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


def load_second_wave_frontier(
    path: str | Path = DEFAULT_SECOND_WAVE_FRONTIER,
) -> SecondWaveFrontier:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Second-wave frontier schema is invalid")
    frontier = _mapping(root.get("frontier"), "frontier")
    raw_candidates = frontier.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("Second-wave candidates must be an array")
    candidates = tuple(_candidate(_mapping(item, "candidate")) for item in raw_candidates)
    trust = _mapping(frontier.get("trust_boundary"), "trust_boundary")
    stable = {
        "frontier_id": frontier.get("frontier_id"),
        "frontier_version": frontier.get("frontier_version"),
        "ticker": frontier.get("ticker"),
        "purpose": frontier.get("purpose"),
        "target": frontier.get("target_additional_training_rows"),
        "holdout": frontier.get("holdout_period"),
        "q4": frontier.get("q4_direct_quarter_derivation_allowed"),
        "candidates": [asdict(item) for item in candidates],
        "trust_boundary": trust,
    }
    return SecondWaveFrontier(
        evidence_id=_sha(stable),
        frontier_id=str(frontier.get("frontier_id", "")),
        frontier_version=str(frontier.get("frontier_version", "")),
        ticker=str(frontier.get("ticker", "")).zfill(6),
        purpose=str(frontier.get("purpose", "")),
        target_additional_training_rows=int(
            str(frontier.get("target_additional_training_rows", 0))
        ),
        holdout_period=str(frontier.get("holdout_period", "")),
        q4_direct_quarter_derivation_allowed=(
            frontier.get("q4_direct_quarter_derivation_allowed") is True
        ),
        candidates=candidates,
        issuer_driver_values_are_exact_numeric_source_facts=(
            trust.get("issuer_driver_values_are_exact_numeric_source_facts") is True
        ),
        product_revenue_certified=trust.get("product_revenue_certified") is True,
        company_profitability_certified=(
            trust.get("company_profitability_certified") is True
        ),
        training_row_promoted=trust.get("training_row_promoted") is True,
        candidate_registration_enables_fit=(
            trust.get("candidate_registration_enables_fit") is True
        ),
        candidate_registration_enables_holdout=(
            trust.get("candidate_registration_enables_holdout") is True
        ),
        numeric_forecast_enabled=trust.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_SECOND_WAVE_FRONTIER",
    "SecondWaveCandidate",
    "SecondWaveDrivers",
    "SecondWaveFrontier",
    "load_second_wave_frontier",
]
