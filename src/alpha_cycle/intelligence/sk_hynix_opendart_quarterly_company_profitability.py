"""Source-bounded SK hynix quarterly company-profitability panel from OpenDART.

OpenDART's all-accounts endpoint documents ``thstrm_amount`` as the three-month amount
for quarterly/semiannual income statements.  The existing provider already normalizes
that field into the financial frame.  This module selects directly reported consolidated
Revenue, Cost of Sales, and Gross Profit facts, requires a single filing revision per
quarter, and reconciles the accounting identity before admitting an observation.

The panel is historical calibration support only.  It is not product profitability and
is not point-in-time backtest evidence because the API is queried at the current date.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

from alpha_cycle.providers.opendart import (
    REPORT_PERIODS,
    FinancialBatch,
    OpenDartReadOnlyClient,
)

DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY = Path(
    "config/skhynix_opendart_quarterly_company_profitability.yaml"
)
DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT = Path(
    "data/private/research/skhynix-opendart-quarterly-company-profitability"
)
DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER = (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT
    / "latest_quarterly_company_profitability.json"
)
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})
_EXPECTED_PERIOD_IDS = (
    "2023Q1",
    "2023Q2",
    "2023Q3",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2025Q1",
    "2025Q2",
    "2025Q3",
    "2026Q1",
)


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


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Quarterly profitability {label} must be an array")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if not result:
        raise ValueError(f"Quarterly profitability {label} cannot be empty")
    return result


@dataclass(frozen=True)
class QuarterlyCompanyProfitabilityPeriodSpec:
    period_id: str
    business_year: int
    report_code: str
    period_end: date

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIOD_IDS:
            raise ValueError("Quarterly profitability period is unsupported")
        if self.report_code not in {"11013", "11012", "11014"}:
            raise ValueError("Quarterly profitability requires Q1/H1/Q3 report code")
        _, month, day = REPORT_PERIODS[self.report_code]
        if self.period_end != date(self.business_year, month, day):
            raise ValueError("Quarterly profitability report code/period end mismatch")


@dataclass(frozen=True)
class QuarterlyCompanyProfitabilityRegistry:
    ticker: str
    issuer_name: str
    source_id: str
    fs_div: str
    periods: tuple[QuarterlyCompanyProfitabilityPeriodSpec, ...]
    revenue_account_ids: tuple[str, ...]
    cost_of_sales_account_ids: tuple[str, ...]
    gross_profit_account_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.ticker != "000660" or self.source_id != "opendart_fnltt_singl_acnt_all":
            raise ValueError("Quarterly profitability registry v1 supports SK hynix/OpenDART only")
        if self.fs_div != "CFS":
            raise ValueError("Quarterly profitability registry requires consolidated statements")
        if tuple(item.period_id for item in self.periods) != _EXPECTED_PERIOD_IDS:
            raise ValueError("Quarterly profitability registry periods are not complete/bound")


@dataclass(frozen=True)
class QuarterlyCompanyProfitabilityObservation:
    period_id: str
    period_end: date
    business_year: int
    report_code: str
    rcept_no: str
    available_date: date
    revenue_krw: int
    cost_of_sales_krw: int
    gross_profit_krw: int
    gross_margin_percent: float
    accounting_identity_delta_krw: int
    raw_payload_sha256: str
    company_profitability_source_facts: bool = True
    product_profitability_source_fact: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIOD_IDS:
            raise ValueError("Quarterly profitability observation period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Quarterly profitability receipt number must be 14 digits")
        if self.available_date > self.period_end.replace(year=self.available_date.year) and False:
            raise ValueError("unreachable")
        if self.revenue_krw <= 0 or self.cost_of_sales_krw < 0:
            raise ValueError("Quarterly profitability revenue/cost values are invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("Quarterly profitability accounting identity does not reconcile")
        if self.accounting_identity_delta_krw != 0:
            raise ValueError("Quarterly profitability identity delta must be zero")
        expected_margin = self.gross_profit_krw / self.revenue_krw * 100.0
        if not math.isfinite(self.gross_margin_percent):
            raise ValueError("Quarterly profitability gross margin must be finite")
        if abs(expected_margin - self.gross_margin_percent) > 1e-12:
            raise ValueError("Quarterly profitability gross margin is inconsistent")
        if not _valid_sha(self.raw_payload_sha256):
            raise ValueError("Quarterly profitability raw payload hash must be SHA-256")
        if not self.company_profitability_source_facts or self.product_profitability_source_fact:
            raise ValueError("Quarterly profitability observation exceeds source boundary")


@dataclass(frozen=True)
class QuarterlyCompanyProfitabilityEvidence:
    evidence_id: str
    evaluation_date: date
    ticker: str
    issuer_name: str
    observations: tuple[QuarterlyCompanyProfitabilityObservation, ...]
    observation_count: int
    calibration_support_only: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Quarterly profitability evidence_id must be SHA-256")
        if self.ticker != "000660":
            raise ValueError("Quarterly profitability evidence supports SK hynix only")
        if tuple(item.period_id for item in self.observations) != _EXPECTED_PERIOD_IDS:
            raise ValueError("Quarterly profitability evidence periods are incomplete")
        if self.observation_count != len(self.observations):
            raise ValueError("Quarterly profitability observation count is inconsistent")
        if any(item.available_date > self.evaluation_date for item in self.observations):
            raise ValueError("Quarterly profitability evidence uses future filing data")
        if (
            not self.calibration_support_only
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Quarterly profitability panel exceeds its trust boundary")


def load_quarterly_company_profitability_registry(
    path: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
) -> QuarterlyCompanyProfitabilityRegistry:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuer"), dict):
        raise ValueError("Quarterly profitability registry must contain issuer")
    issuer = cast(dict[object, object], payload["issuer"])
    raw_periods = issuer.get("periods")
    if not isinstance(raw_periods, list):
        raise ValueError("Quarterly profitability periods must be an array")
    periods: list[QuarterlyCompanyProfitabilityPeriodSpec] = []
    for raw_period in raw_periods:
        if not isinstance(raw_period, dict):
            raise ValueError("Quarterly profitability period must be an object")
        raw = cast(dict[object, object], raw_period)
        periods.append(
            QuarterlyCompanyProfitabilityPeriodSpec(
                period_id=str(raw.get("period_id", "")).strip(),
                business_year=int(str(raw.get("business_year", "0"))),
                report_code=str(raw.get("report_code", "")).strip(),
                period_end=date.fromisoformat(str(raw.get("period_end", ""))),
            )
        )
    account_ids = issuer.get("account_ids")
    if not isinstance(account_ids, dict):
        raise ValueError("Quarterly profitability account_ids must be an object")
    accounts = cast(dict[object, object], account_ids)
    return QuarterlyCompanyProfitabilityRegistry(
        ticker=str(issuer.get("ticker", "")).strip().zfill(6),
        issuer_name=str(issuer.get("issuer_name", "")).strip(),
        source_id=str(issuer.get("source_id", "")).strip(),
        fs_div=str(issuer.get("fs_div", "")).strip(),
        periods=tuple(periods),
        revenue_account_ids=_string_tuple(accounts.get("revenue"), "account_ids.revenue"),
        cost_of_sales_account_ids=_string_tuple(
            accounts.get("cost_of_sales"), "account_ids.cost_of_sales"
        ),
        gross_profit_account_ids=_string_tuple(
            accounts.get("gross_profit"), "account_ids.gross_profit"
        ),
    )


def _metric_parts(metric: object) -> tuple[str, str]:
    text = str(metric).strip()
    if ":" not in text:
        return "", ""
    statement, remainder = text.split(":", 1)
    account_key = remainder.split(":", 1)[0].split("#", 1)[0]
    return statement, account_key


def _integral_krw(value: object, label: str) -> int:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Quarterly profitability {label} is not numeric") from exc
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Quarterly profitability {label} must be integral KRW")
    return int(amount)


def _select_account(
    frame: pd.DataFrame,
    account_ids: tuple[str, ...],
    *,
    label: str,
) -> tuple[int, str, date]:
    accepted = {item.casefold() for item in account_ids}
    matches: list[tuple[int, str, date]] = []
    for row in frame.itertuples(index=False):
        statement, account_key = _metric_parts(getattr(row, "metric"))
        if statement not in _ALLOWED_STATEMENTS or account_key.casefold() not in accepted:
            continue
        revision_id = str(getattr(row, "revision_id")).strip()
        available_date = cast(date, getattr(row, "available_date"))
        matches.append(
            (
                _integral_krw(getattr(row, "value"), label),
                revision_id,
                available_date,
            )
        )
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"Quarterly profitability account must resolve uniquely: {label} count={len(unique)}"
        )
    return unique[0]


def extract_quarterly_company_profitability(
    registry: QuarterlyCompanyProfitabilityRegistry,
    spec: QuarterlyCompanyProfitabilityPeriodSpec,
    batch: FinancialBatch,
) -> QuarterlyCompanyProfitabilityObservation:
    if batch.corp.stock_code != registry.ticker:
        raise ValueError("Quarterly profitability financial batch has another ticker")
    frame = batch.frame
    revenue, revenue_receipt, revenue_date = _select_account(
        frame,
        registry.revenue_account_ids,
        label="revenue",
    )
    cost, cost_receipt, cost_date = _select_account(
        frame,
        registry.cost_of_sales_account_ids,
        label="cost_of_sales",
    )
    gross, gross_receipt, gross_date = _select_account(
        frame,
        registry.gross_profit_account_ids,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    available_dates = {revenue_date, cost_date, gross_date}
    if len(receipts) != 1 or len(available_dates) != 1:
        raise ValueError("Quarterly profitability selected accounts cross filing revisions")
    raw_sha = _sha_payload(batch.raw_payload)
    identity_delta = revenue - cost - gross
    if identity_delta != 0:
        raise ValueError(
            "Quarterly profitability direct Revenue-CostOfSales-GrossProfit identity fails: "
            f"period={spec.period_id} delta={identity_delta}"
        )
    return QuarterlyCompanyProfitabilityObservation(
        period_id=spec.period_id,
        period_end=spec.period_end,
        business_year=spec.business_year,
        report_code=spec.report_code,
        rcept_no=next(iter(receipts)),
        available_date=next(iter(available_dates)),
        revenue_krw=revenue,
        cost_of_sales_krw=cost,
        gross_profit_krw=gross,
        gross_margin_percent=gross / revenue * 100.0,
        accounting_identity_delta_krw=identity_delta,
        raw_payload_sha256=raw_sha,
    )


def collect_quarterly_company_profitability(
    client: OpenDartReadOnlyClient,
    registry: QuarterlyCompanyProfitabilityRegistry,
    *,
    evaluation_date: date,
) -> tuple[QuarterlyCompanyProfitabilityEvidence, dict[str, object]]:
    corp = client.resolve_stock_codes([registry.ticker])[registry.ticker]
    observations: list[QuarterlyCompanyProfitabilityObservation] = []
    raw_payloads: dict[str, object] = {}
    for spec in registry.periods:
        batch = client.financial_statements(
            corp,
            business_year=spec.business_year,
            report_code=spec.report_code,
            fs_div=registry.fs_div,
        )
        observation = extract_quarterly_company_profitability(registry, spec, batch)
        if observation.available_date > evaluation_date:
            raise ValueError(
                f"Quarterly profitability period is not observable: {spec.period_id}"
            )
        observations.append(observation)
        raw_payloads[spec.period_id] = batch.raw_payload
    source_payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "ticker": registry.ticker,
        "observations": [asdict(item) for item in observations],
        "calibration_support_only": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
    }
    evidence = QuarterlyCompanyProfitabilityEvidence(
        evidence_id=_sha_payload(source_payload),
        evaluation_date=evaluation_date,
        ticker=registry.ticker,
        issuer_name=registry.issuer_name,
        observations=tuple(observations),
        observation_count=len(observations),
    )
    return evidence, raw_payloads


def _evidence_payload(evidence: QuarterlyCompanyProfitabilityEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "observations": [
            {
                **asdict(item),
                "period_end": item.period_end.isoformat(),
                "available_date": item.available_date.isoformat(),
            }
            for item in evidence.observations
        ],
        "observation_count": evidence.observation_count,
        "calibration_support_only": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "product_profitability_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }


def capture_quarterly_company_profitability(
    client: OpenDartReadOnlyClient,
    registry: QuarterlyCompanyProfitabilityRegistry,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence, raw_payloads = collect_quarterly_company_profitability(
        client,
        registry,
        evaluation_date=evaluation_date,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < evaluation_date:
        raise ValueError("captured_at cannot precede evaluation_date in Asia/Seoul")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Quarterly profitability artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        payload = _evidence_payload(evidence)
        (temporary / "panel.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        raw_dir = temporary / "raw"
        raw_dir.mkdir()
        for period_id, raw in raw_payloads.items():
            (raw_dir / f"{period_id}.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "skhynix_opendart_quarterly_company_profitability_captured",
            "captured_at": captured.isoformat(),
            "files": ["panel.json", *[f"raw/{item}.json" for item in raw_payloads]],
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
        "status": "skhynix_opendart_quarterly_company_profitability_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "panel_path": str((directory / "panel.json").resolve()),
        "raw_directory": str((directory / "raw").resolve()),
    }
    pointer_path = root / "latest_quarterly_company_profitability.json"
    temporary_pointer = root / ".latest_quarterly_company_profitability.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


__all__ = [
    "DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT",
    "DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER",
    "DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY",
    "QuarterlyCompanyProfitabilityEvidence",
    "QuarterlyCompanyProfitabilityObservation",
    "QuarterlyCompanyProfitabilityPeriodSpec",
    "QuarterlyCompanyProfitabilityRegistry",
    "capture_quarterly_company_profitability",
    "collect_quarterly_company_profitability",
    "extract_quarterly_company_profitability",
    "load_quarterly_company_profitability_registry",
]
