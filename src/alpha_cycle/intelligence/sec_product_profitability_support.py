"""Historical SK hynix profitability calibration support from official SEC bytes.

This layer aligns directly disclosed product revenue with company gross profit and gross
margin for historical periods. It is calibration support only: it never discloses or
infers DRAM/NAND product margins and cannot become a current profitability baseline.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.intelligence.sec_company_actual import (
    SEC_ARCHIVES_ROOT,
    SEC_SUBMISSIONS_ROOT,
    download_sec_bytes,
    extract_sec_visible_parts,
)

DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY = Path(
    "config/semiconductor_sec_product_profitability_support.yaml"
)
DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT = Path(
    "data/private/research/sec-product-profitability-support"
)
DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER = (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT / "latest_sec_product_profitability_support.json"
)
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
_REVENUE_RECONCILIATION_TOLERANCE_KRW_BILLION = 1.0
_MARGIN_RECONCILIATION_TOLERANCE_PP = 0.11
_PERIOD_ORDER = ("q1_2026", "q1_2025", "fy2025", "fy2024", "fy2023")
_PERIOD_DATES = {
    "q1_2026": (date(2026, 1, 1), date(2026, 3, 31)),
    "q1_2025": (date(2025, 1, 1), date(2025, 3, 31)),
    "fy2025": (date(2025, 1, 1), date(2025, 12, 31)),
    "fy2024": (date(2024, 1, 1), date(2024, 12, 31)),
    "fy2023": (date(2023, 1, 1), date(2023, 12, 31)),
}


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"SEC product-profitability {label} must be boolean")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"SEC product-profitability {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"SEC product-profitability {label} cannot be empty")
    return result


@dataclass(frozen=True)
class SecProductProfitabilitySupportSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    cik: str
    form: str
    filing_date: date
    expected_accession_number: str
    expected_primary_document: str
    parser_id: str
    calibration_support_only: bool
    product_profitability_source_fact: bool
    current_baseline_eligible: bool
    numeric_forecast_enabled: bool
    decision_score_enabled: bool
    required_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.ticker != "000660":
            raise ValueError("SEC product-profitability support v1 supports SK hynix only")
        if self.source_id != "sec_edgar" or self.form != "424B4":
            raise ValueError("SEC product-profitability support requires official 424B4")
        if len(self.cik) != 10 or not self.cik.isdigit():
            raise ValueError("SEC product-profitability CIK must be ten digits")
        parts = self.expected_accession_number.split("-")
        if (
            len(parts) != 3
            or tuple(len(item) for item in parts) != (10, 2, 6)
            or not all(item.isdigit() for item in parts)
        ):
            raise ValueError("SEC product-profitability accession is invalid")
        if not self.expected_primary_document.endswith((".htm", ".html")):
            raise ValueError("SEC product-profitability primary document must be HTML")
        if (
            not self.calibration_support_only
            or self.product_profitability_source_fact
            or self.current_baseline_eligible
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC product-profitability spec exceeds calibration-support boundary")
        if not self.required_identity_anchors:
            raise ValueError("SEC product-profitability support requires identity anchors")

    @property
    def submissions_url(self) -> str:
        return f"{SEC_SUBMISSIONS_ROOT}/CIK{self.cik}.json"

    @property
    def filing_url(self) -> str:
        accession = self.expected_accession_number.replace("-", "")
        return (
            f"{SEC_ARCHIVES_ROOT}/{int(self.cik)}/{accession}/"
            f"{self.expected_primary_document}"
        )


@dataclass(frozen=True)
class HistoricalProductProfitabilityConstraint:
    period_id: str
    period_start: date
    period_end: date
    unit: str
    total_revenue: float
    dram_revenue: float
    nand_revenue: float
    other_products_revenue: float
    dram_share_percent: float
    nand_share_percent: float
    other_share_percent: float
    product_revenue_reconciliation_delta_krw_billion: float
    gross_profit: float
    gross_margin_percent: float
    gross_margin_reconciliation_delta_pp: float
    direct_product_revenue_reconciled: bool
    company_gross_margin_reconciled: bool

    def __post_init__(self) -> None:
        if self.period_id not in _PERIOD_ORDER:
            raise ValueError("SEC product-profitability period is unsupported")
        if (self.period_start, self.period_end) != _PERIOD_DATES[self.period_id]:
            raise ValueError("SEC product-profitability period dates are inconsistent")
        if self.unit != "KRW_billion":
            raise ValueError("SEC product-profitability support normalizes to KRW_billion")
        values = (
            self.total_revenue,
            self.dram_revenue,
            self.nand_revenue,
            self.other_products_revenue,
            self.dram_share_percent,
            self.nand_share_percent,
            self.other_share_percent,
            self.product_revenue_reconciliation_delta_krw_billion,
            self.gross_profit,
            self.gross_margin_percent,
            self.gross_margin_reconciliation_delta_pp,
        )
        if any(not math.isfinite(item) for item in values):
            raise ValueError("SEC product-profitability values must be finite")
        if min(
            self.total_revenue,
            self.dram_revenue,
            self.nand_revenue,
            self.other_products_revenue,
        ) <= 0:
            raise ValueError("SEC product-profitability revenue values must be positive")
        product_sum = self.dram_revenue + self.nand_revenue + self.other_products_revenue
        revenue_delta = product_sum - self.total_revenue
        if abs(revenue_delta - self.product_revenue_reconciliation_delta_krw_billion) > 1e-9:
            raise ValueError("SEC product-profitability revenue delta is inconsistent")
        if abs(revenue_delta) > _REVENUE_RECONCILIATION_TOLERANCE_KRW_BILLION:
            raise ValueError("SEC product-profitability product revenue does not reconcile")
        share_sum = self.dram_share_percent + self.nand_share_percent + self.other_share_percent
        if abs(share_sum - 100.0) > 0.11:
            raise ValueError("SEC product-profitability product shares do not reconcile")
        calculated_margin = self.gross_profit / self.total_revenue * 100.0
        margin_delta = calculated_margin - self.gross_margin_percent
        if abs(margin_delta - self.gross_margin_reconciliation_delta_pp) > 1e-9:
            raise ValueError("SEC product-profitability margin delta is inconsistent")
        if abs(margin_delta) > _MARGIN_RECONCILIATION_TOLERANCE_PP:
            raise ValueError("SEC product-profitability gross margin does not reconcile")
        if not self.direct_product_revenue_reconciled or not self.company_gross_margin_reconciled:
            raise ValueError("SEC product-profitability required reconciliations are false")


@dataclass(frozen=True)
class SecProductProfitabilitySupportEvidence:
    evidence_id: str
    observed_date: date
    document_id: str
    ticker: str
    issuer_name: str
    accession_number: str
    primary_document: str
    filing_date: date
    submissions_sha256: str
    filing_sha256: str
    observations: tuple[HistoricalProductProfitabilityConstraint, ...]
    observation_count: int
    independent_non_overlapping_period_count: int
    overlapping_periods_present: bool
    calibration_support_only: bool = True
    product_profitability_source_fact: bool = False
    current_baseline_eligible: bool = False
    direct_product_profitability_observations: int = 0
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (self.evidence_id, self.submissions_sha256, self.filing_sha256)
        if any(not _valid_sha(item) for item in hashes):
            raise ValueError("SEC product-profitability evidence hashes must be SHA-256")
        if self.filing_date > self.observed_date:
            raise ValueError("SEC product-profitability evidence cannot predate filing")
        if tuple(item.period_id for item in self.observations) != _PERIOD_ORDER:
            raise ValueError("SEC product-profitability observations are not in bound order")
        if self.observation_count != len(self.observations):
            raise ValueError("SEC product-profitability observation count is inconsistent")
        independent = _max_non_overlapping_periods(self.observations)
        if self.independent_non_overlapping_period_count != independent:
            raise ValueError("SEC product-profitability independent period count is inconsistent")
        if self.overlapping_periods_present != (independent < len(self.observations)):
            raise ValueError("SEC product-profitability overlap flag is inconsistent")
        if (
            not self.calibration_support_only
            or self.product_profitability_source_fact
            or self.current_baseline_eligible
            or self.direct_product_profitability_observations != 0
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SEC product-profitability evidence exceeds support boundary")


def load_sec_product_profitability_registry(
    path: str | Path = DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY,
) -> dict[str, SecProductProfitabilitySupportSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("SEC product-profitability registry must contain issuers")
    result: dict[str, SecProductProfitabilitySupportSpec] = {}
    issuers = cast(dict[object, object], payload["issuers"])
    for raw_ticker, raw_issuer in issuers.items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_issuer, dict):
            raise ValueError(f"SEC product-profitability issuer must be an object: {ticker}")
        issuer = cast(dict[object, object], raw_issuer)
        filings = issuer.get("filings", {})
        if not isinstance(filings, dict):
            raise ValueError(f"SEC product-profitability filings must be an object: {ticker}")
        for raw_id, raw_value in cast(dict[object, object], filings).items():
            document_id = str(raw_id).strip()
            if not isinstance(raw_value, dict):
                raise ValueError(f"SEC product-profitability filing must be object: {document_id}")
            raw = cast(dict[object, object], raw_value)
            spec = SecProductProfitabilitySupportSpec(
                document_id=document_id,
                ticker=ticker,
                issuer_name=str(issuer.get("issuer_name", "")).strip(),
                source_id=str(raw.get("source_id", "")).strip(),
                cik=str(raw.get("cik", "")).strip().zfill(10),
                form=str(raw.get("form", "")).strip(),
                filing_date=date.fromisoformat(str(raw.get("filing_date", ""))),
                expected_accession_number=str(raw.get("expected_accession_number", "")).strip(),
                expected_primary_document=str(raw.get("expected_primary_document", "")).strip(),
                parser_id=str(raw.get("parser_id", "")).strip(),
                calibration_support_only=_strict_bool(
                    raw.get("calibration_support_only"), "calibration_support_only"
                ),
                product_profitability_source_fact=_strict_bool(
                    raw.get("product_profitability_source_fact"),
                    "product_profitability_source_fact",
                ),
                current_baseline_eligible=_strict_bool(
                    raw.get("current_baseline_eligible"), "current_baseline_eligible"
                ),
                numeric_forecast_enabled=_strict_bool(
                    raw.get("numeric_forecast_enabled"), "numeric_forecast_enabled"
                ),
                decision_score_enabled=_strict_bool(
                    raw.get("decision_score_enabled"), "decision_score_enabled"
                ),
                required_identity_anchors=_string_tuple(
                    raw.get("required_identity_anchors", []), "required_identity_anchors"
                ),
            )
            if document_id in result:
                raise ValueError(f"SEC product-profitability filing duplicated: {document_id}")
            result[document_id] = spec
    if not result:
        raise ValueError("SEC product-profitability registry is empty")
    return result


def discover_sec_product_profitability_filing(
    spec: SecProductProfitabilitySupportSpec,
    submissions_bytes: bytes,
) -> None:
    try:
        payload: object = json.loads(submissions_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SEC product-profitability submissions payload is invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("SEC product-profitability submissions payload must be object")
    filings = cast(dict[str, object], payload).get("filings")
    if not isinstance(filings, dict):
        raise ValueError("SEC product-profitability submissions missing filings")
    recent = cast(dict[str, object], filings).get("recent")
    if not isinstance(recent, dict):
        raise ValueError("SEC product-profitability submissions missing recent filings")
    recent_map = cast(dict[str, object], recent)
    keys = ("accessionNumber", "filingDate", "form", "primaryDocument")
    columns: dict[str, list[object]] = {}
    for key in keys:
        value = recent_map.get(key)
        if not isinstance(value, list):
            raise ValueError(f"SEC product-profitability recent.{key} must be array")
        columns[key] = value
    lengths = {len(item) for item in columns.values()}
    if len(lengths) != 1:
        raise ValueError("SEC product-profitability recent filing arrays are misaligned")
    matches = 0
    for index in range(next(iter(lengths), 0)):
        if (
            str(columns["accessionNumber"][index]).strip() == spec.expected_accession_number
            and str(columns["filingDate"][index]).strip() == spec.filing_date.isoformat()
            and str(columns["form"][index]).strip() == spec.form
            and str(columns["primaryDocument"][index]).strip()
            == spec.expected_primary_document
        ):
            matches += 1
    if matches != 1:
        raise ValueError(
            "Pinned SEC product-profitability filing must resolve exactly once: "
            f"count={matches}"
        )


def _normalized_text(filing_bytes: bytes) -> str:
    return " ".join(" ".join(extract_sec_visible_parts(filing_bytes)).split())


def _require_anchor(text: str, anchor: str) -> None:
    if " ".join(anchor.split()).casefold() not in text.casefold():
        raise ValueError(f"SEC product-profitability identity anchor missing: {anchor}")


def _section(text: str, start_anchor: str, end_anchor: str) -> str:
    folded = text.casefold()
    start = folded.find(start_anchor.casefold())
    if start < 0:
        raise ValueError(f"SEC product-profitability section start missing: {start_anchor}")
    end = folded.find(end_anchor.casefold(), start + len(start_anchor))
    if end < 0:
        raise ValueError(f"SEC product-profitability section end missing: {end_anchor}")
    return text[start:end]


def _row_pairs(
    section: str,
    start_pattern: str,
    end_pattern: str,
    label: str,
) -> tuple[tuple[float, float], ...]:
    start_match = re.search(start_pattern, section, flags=re.IGNORECASE)
    if start_match is None:
        raise ValueError(f"SEC product-profitability row missing: {label}")
    tail = section[start_match.end() :]
    end_match = re.search(end_pattern, tail, flags=re.IGNORECASE)
    if end_match is None:
        raise ValueError(f"SEC product-profitability row end missing: {label}")
    row = tail[: end_match.start()]
    pairs = re.findall(
        r"(?:W\s+)?([0-9][0-9,]*)\s+([0-9]+(?:\.[0-9]+)?)\s*%",
        row,
        flags=re.IGNORECASE,
    )
    result = tuple((float(amount.replace(",", "")), float(share)) for amount, share in pairs)
    if len(result) != len(_PERIOD_ORDER):
        raise ValueError(
            f"SEC product-profitability row must resolve five periods: {label} count={len(result)}"
        )
    return result


def _unique_values(
    text: str,
    pattern: str,
    count: int,
    label: str,
) -> tuple[float, ...]:
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    parsed = [tuple(float(item.replace(",", "")) for item in match) for match in matches]
    values = tuple(dict.fromkeys(parsed))
    if len(values) != 1 or len(values[0]) != count:
        raise ValueError(f"SEC product-profitability narrative must resolve uniquely: {label}")
    return values[0]


def _profitability_values(text: str) -> dict[str, tuple[float, float]]:
    q1_profit = _unique_values(
        text,
        r"gross profit increased by\s+[0-9.]+%[^.]*?to\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in the first quarter of 2026\s+from\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in the first quarter of 2025",
        2,
        "q1_gross_profit",
    )
    q1_margin = _unique_values(
        text,
        r"gross profit margin increased to\s+([0-9.]+)%\s+in the first quarter of 2026\s+from\s+([0-9.]+)%\s+in the first quarter of 2025",
        2,
        "q1_gross_margin",
    )
    annual_profit = _unique_values(
        text,
        r"gross profit increased by\s+[0-9.]+%[^.]*?to\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in 2025\s+from\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in 2024",
        2,
        "annual_gross_profit",
    )
    annual_margin = _unique_values(
        text,
        r"gross profit margin increased to\s+([0-9.]+)%\s+in 2025\s+from\s+([0-9.]+)%\s+in 2024",
        2,
        "annual_gross_margin",
    )
    prior_profit = _unique_values(
        text,
        r"recorded gross profit of\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in 2024\s+compared to gross loss of\s+(?:W\s+)?([0-9][0-9,]*)\s+billion\s+in 2023",
        2,
        "prior_gross_profit",
    )
    prior_margin = _unique_values(
        text,
        r"gross profit margin of\s+([0-9.]+)%\s+in 2024\s+compared to gross loss margin of\s+([0-9.]+)%\s+in 2023",
        2,
        "prior_gross_margin",
    )
    if annual_profit[1] != prior_profit[0] or annual_margin[1] != prior_margin[0]:
        raise ValueError("SEC product-profitability overlapping annual narratives disagree")
    return {
        "q1_2026": (q1_profit[0], q1_margin[0]),
        "q1_2025": (q1_profit[1], q1_margin[1]),
        "fy2025": (annual_profit[0], annual_margin[0]),
        "fy2024": (annual_profit[1], annual_margin[1]),
        "fy2023": (-prior_profit[1], -prior_margin[1]),
    }


def _max_non_overlapping_periods(
    observations: tuple[HistoricalProductProfitabilityConstraint, ...],
) -> int:
    selected_end: date | None = None
    count = 0
    for item in sorted(observations, key=lambda value: (value.period_end, value.period_start)):
        if selected_end is None or item.period_start > selected_end:
            count += 1
            selected_end = item.period_end
    return count


def parse_sec_product_profitability_support_html(
    spec: SecProductProfitabilitySupportSpec,
    filing_bytes: bytes,
) -> tuple[HistoricalProductProfitabilityConstraint, ...]:
    if spec.parser_id != "skhynix_sec_424b4_product_profitability_support_v1":
        raise ValueError("SEC product-profitability parser received unsupported parser_id")
    text = _normalized_text(filing_bytes)
    for anchor in spec.required_identity_anchors:
        _require_anchor(text, anchor)
    product_section = _section(
        text,
        "The following table sets forth our revenue by principal product category and the related percentage data for the periods indicated.",
        "DRAMs are a type",
    )
    dram = _row_pairs(product_section, r"\bDRAM\b", r"\bNAND\s+Flash\b", "dram")
    nand = _row_pairs(product_section, r"\bNAND\s+Flash\b", r"\bOther\s+Products\b", "nand")
    other = _row_pairs(product_section, r"\bOther\s+Products\b", r"\bTotal\b", "other")
    total = _row_pairs(product_section, r"\bTotal\b", r"$", "total")
    profits = _profitability_values(text)
    observations: list[HistoricalProductProfitabilityConstraint] = []
    for index, period_id in enumerate(_PERIOD_ORDER):
        total_revenue, total_share = total[index]
        dram_revenue, dram_share = dram[index]
        nand_revenue, nand_share = nand[index]
        other_revenue, other_share = other[index]
        if abs(total_share - 100.0) > 1e-9:
            raise ValueError("SEC product-profitability total share must be 100%")
        gross_profit, gross_margin = profits[period_id]
        revenue_delta = dram_revenue + nand_revenue + other_revenue - total_revenue
        margin_delta = gross_profit / total_revenue * 100.0 - gross_margin
        start, end = _PERIOD_DATES[period_id]
        observations.append(
            HistoricalProductProfitabilityConstraint(
                period_id=period_id,
                period_start=start,
                period_end=end,
                unit="KRW_billion",
                total_revenue=total_revenue,
                dram_revenue=dram_revenue,
                nand_revenue=nand_revenue,
                other_products_revenue=other_revenue,
                dram_share_percent=dram_share,
                nand_share_percent=nand_share,
                other_share_percent=other_share,
                product_revenue_reconciliation_delta_krw_billion=revenue_delta,
                gross_profit=gross_profit,
                gross_margin_percent=gross_margin,
                gross_margin_reconciliation_delta_pp=margin_delta,
                direct_product_revenue_reconciled=(
                    abs(revenue_delta) <= _REVENUE_RECONCILIATION_TOLERANCE_KRW_BILLION
                ),
                company_gross_margin_reconciled=(
                    abs(margin_delta) <= _MARGIN_RECONCILIATION_TOLERANCE_PP
                ),
            )
        )
    return tuple(observations)


def build_sec_product_profitability_support_evidence(
    spec: SecProductProfitabilitySupportSpec,
    *,
    observed_date: date,
    submissions_bytes: bytes,
    filing_bytes: bytes,
) -> SecProductProfitabilitySupportEvidence:
    if spec.filing_date > observed_date:
        raise ValueError("SEC product-profitability filing is not yet observable")
    discover_sec_product_profitability_filing(spec, submissions_bytes)
    observations = parse_sec_product_profitability_support_html(spec, filing_bytes)
    source_payload = {
        "document_id": spec.document_id,
        "observed_date": observed_date.isoformat(),
        "submissions_sha256": _sha_bytes(submissions_bytes),
        "filing_sha256": _sha_bytes(filing_bytes),
        "observations": [asdict(item) for item in observations],
        "calibration_support_only": True,
        "product_profitability_source_fact": False,
    }
    independent = _max_non_overlapping_periods(observations)
    return SecProductProfitabilitySupportEvidence(
        evidence_id=_sha_payload(source_payload),
        observed_date=observed_date,
        document_id=spec.document_id,
        ticker=spec.ticker,
        issuer_name=spec.issuer_name,
        accession_number=spec.expected_accession_number,
        primary_document=spec.expected_primary_document,
        filing_date=spec.filing_date,
        submissions_sha256=_sha_bytes(submissions_bytes),
        filing_sha256=_sha_bytes(filing_bytes),
        observations=observations,
        observation_count=len(observations),
        independent_non_overlapping_period_count=independent,
        overlapping_periods_present=independent < len(observations),
    )


def _evidence_payload(evidence: SecProductProfitabilitySupportEvidence) -> dict[str, object]:
    observations = [
        {
            **asdict(item),
            "period_start": item.period_start.isoformat(),
            "period_end": item.period_end.isoformat(),
        }
        for item in evidence.observations
    ]
    return {
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "document_id": evidence.document_id,
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "accession_number": evidence.accession_number,
        "primary_document": evidence.primary_document,
        "filing_date": evidence.filing_date.isoformat(),
        "submissions_sha256": evidence.submissions_sha256,
        "filing_sha256": evidence.filing_sha256,
        "observations": observations,
        "observation_count": evidence.observation_count,
        "independent_non_overlapping_period_count": evidence.independent_non_overlapping_period_count,
        "overlapping_periods_present": evidence.overlapping_periods_present,
        "calibration_support_only": True,
        "product_profitability_source_fact": False,
        "current_baseline_eligible": False,
        "direct_product_profitability_observations": 0,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }


def capture_sec_product_profitability_support(
    spec: SecProductProfitabilitySupportSpec,
    *,
    observed_date: date,
    user_agent: str,
    output: str | Path = DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT,
    captured_at: datetime | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    submissions_bytes = download_sec_bytes(
        spec.submissions_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    filing_bytes = download_sec_bytes(
        spec.filing_url,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    evidence = build_sec_product_profitability_support_evidence(
        spec,
        observed_date=observed_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < observed_date:
        raise ValueError("captured_at cannot precede observed_date in Asia/Seoul")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"SEC product-profitability artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "sec_submissions.json").write_bytes(submissions_bytes)
        (temporary / "sec_filing.html").write_bytes(filing_bytes)
        payload = _evidence_payload(evidence)
        (temporary / "support.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "sec_product_profitability_support_captured",
            "captured_at": captured.isoformat(),
            "files": ["sec_submissions.json", "sec_filing.html", "support.json"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    pointer = {
        **_evidence_payload(evidence),
        "schema_version": 1,
        "status": "sec_product_profitability_support_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "support_path": str((directory / "support.json").resolve()),
        "submissions_path": str((directory / "sec_submissions.json").resolve()),
        "filing_path": str((directory / "sec_filing.html").resolve()),
    }
    pointer_path = root / "latest_sec_product_profitability_support.json"
    temporary_pointer = root / ".latest_sec_product_profitability_support.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


__all__ = [
    "DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT",
    "DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER",
    "DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY",
    "HistoricalProductProfitabilityConstraint",
    "SecProductProfitabilitySupportEvidence",
    "SecProductProfitabilitySupportSpec",
    "build_sec_product_profitability_support_evidence",
    "capture_sec_product_profitability_support",
    "discover_sec_product_profitability_filing",
    "load_sec_product_profitability_registry",
    "parse_sec_product_profitability_support_html",
]
