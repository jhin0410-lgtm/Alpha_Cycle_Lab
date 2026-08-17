"""Isolated OpenDART company-profitability probe for pre-2023 SK hynix quarters.

The probe is independent of product-revenue parsing. It reuses only the canonical account
ID contract and OpenDART all-accounts endpoint semantics, archives each current API raw
payload, and verifies Revenue - CostOfSales = GrossProfit for 2021Q1-Q3 and 2022Q1-Q3.

These observations are current-retrieval historical source facts, not point-in-time vintage
evidence and not product profitability. They cannot promote a frontier row or enable fit.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
    load_quarterly_company_profitability_registry,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    HistoricalExpansionCandidate,
    HistoricalExpansionFrontier,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT = Path(
    "data/private/research/skhynix-profitability-historical-expansion-company-probe"
)
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})


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


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"Expansion company profitability {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Expansion company profitability {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Expansion company profitability {label} must be integral KRW")
    return int(amount)


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_payload, dict):
        raise ValueError("Expansion company profitability raw payload must be an object")
    financials = cast(dict[object, object], raw_payload).get("financials")
    if not isinstance(financials, dict):
        raise ValueError("Expansion company profitability raw payload lacks financials")
    raw_rows = cast(dict[object, object], financials).get("list")
    if not isinstance(raw_rows, list):
        raise ValueError("Expansion company profitability financial list must be an array")
    rows: list[dict[str, object]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("Expansion company profitability financial row must be an object")
        rows.append({str(key): value for key, value in cast(dict[object, object], row).items()})
    if not rows:
        raise ValueError("Expansion company profitability financial list is empty")
    return tuple(rows)


def _select_account(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    candidate: HistoricalExpansionCandidate,
    *,
    label: str,
) -> tuple[int, str, date]:
    accepted = {item.casefold() for item in account_ids}
    year = candidate.period_end.year
    report_code = candidate.company_profitability_report_code
    matches: list[tuple[int, str, date]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_report_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(year):
            continue
        if row_report_code and row_report_code != report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        if len(receipt) != 14 or not receipt.isdigit():
            raise ValueError(f"Expansion company profitability {label} receipt is invalid")
        available_date = date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))
        matches.append(
            (
                _integral_krw(row.get("thstrm_amount"), label),
                receipt,
                available_date,
            )
        )
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"Expansion company profitability account must resolve uniquely: "
            f"{candidate.period_id} {label} count={len(unique)}"
        )
    return unique[0]


@dataclass(frozen=True)
class HistoricalExpansionCompanyProfitabilityObservation:
    period_id: str
    period_end: date
    report_code: str
    rcept_no: str
    available_date: date
    revenue_krw: int
    cost_of_sales_krw: int
    gross_profit_krw: int
    gross_margin_percent: float
    raw_payload_sha256: str
    current_retrieval_historical_source_fact: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    product_profitability_source_fact: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in {
            "2021Q1",
            "2021Q2",
            "2021Q3",
            "2022Q1",
            "2022Q2",
            "2022Q3",
        }:
            raise ValueError("Expansion company profitability period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Expansion company profitability receipt must be 14 digits")
        if self.revenue_krw <= 0 or self.cost_of_sales_krw < 0:
            raise ValueError("Expansion company profitability values are invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("Expansion company profitability accounting identity failed")
        expected_margin = self.gross_profit_krw / self.revenue_krw * 100.0
        if not math.isfinite(self.gross_margin_percent):
            raise ValueError("Expansion company profitability gross margin is not finite")
        if abs(expected_margin - self.gross_margin_percent) > 1e-12:
            raise ValueError("Expansion company profitability gross margin is inconsistent")
        if len(self.raw_payload_sha256) != 64:
            raise ValueError("Expansion company profitability raw hash must be SHA-256")
        if (
            not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.product_profitability_source_fact
        ):
            raise ValueError("Expansion company profitability exceeds source boundary")


@dataclass(frozen=True)
class HistoricalExpansionCompanyProbePeriodResult:
    period_id: str
    success: bool
    observation: HistoricalExpansionCompanyProfitabilityObservation | None
    raw_payload_path: str | None
    error_type: str | None
    error: str | None
    frontier_promoted: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.success != (self.observation is not None and self.raw_payload_path is not None):
            raise ValueError("Expansion company probe success state is inconsistent")
        if self.success and (self.error_type is not None or self.error is not None):
            raise ValueError("Successful expansion company probe cannot retain an error")
        if not self.success and (self.error_type is None or self.error is None):
            raise ValueError("Failed expansion company probe must retain an error")
        if self.frontier_promoted or self.training_row_promoted or self.fit_enabled:
            raise ValueError("Expansion company probe exceeded isolated trust boundary")


def extract_expansion_company_profitability_observation(
    candidate: HistoricalExpansionCandidate,
    raw_payload: object,
    *,
    revenue_account_ids: tuple[str, ...],
    cost_of_sales_account_ids: tuple[str, ...],
    gross_profit_account_ids: tuple[str, ...],
) -> HistoricalExpansionCompanyProfitabilityObservation:
    rows = _financial_rows(raw_payload)
    revenue, revenue_receipt, revenue_date = _select_account(
        rows,
        revenue_account_ids,
        candidate,
        label="revenue",
    )
    cost, cost_receipt, cost_date = _select_account(
        rows,
        cost_of_sales_account_ids,
        candidate,
        label="cost_of_sales",
    )
    gross, gross_receipt, gross_date = _select_account(
        rows,
        gross_profit_account_ids,
        candidate,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    dates = {revenue_date, cost_date, gross_date}
    if len(receipts) != 1 or len(dates) != 1:
        raise ValueError("Expansion company profitability selected accounts cross revisions")
    if revenue - cost - gross != 0:
        raise ValueError(
            "Expansion company profitability direct accounting identity fails: "
            f"{candidate.period_id} delta={revenue - cost - gross}"
        )
    receipt = next(iter(receipts))
    available_date = next(iter(dates))
    return HistoricalExpansionCompanyProfitabilityObservation(
        period_id=candidate.period_id,
        period_end=candidate.period_end,
        report_code=candidate.company_profitability_report_code,
        rcept_no=receipt,
        available_date=available_date,
        revenue_krw=revenue,
        cost_of_sales_krw=cost,
        gross_profit_krw=gross,
        gross_margin_percent=gross / revenue * 100.0,
        raw_payload_sha256=_sha_payload(raw_payload),
    )


def run_expansion_company_profitability_probe(
    client: OpenDartReadOnlyClient,
    frontier: HistoricalExpansionFrontier,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT,
    template_registry: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
) -> tuple[HistoricalExpansionCompanyProbePeriodResult, ...]:
    template = load_quarterly_company_profitability_registry(template_registry)
    if frontier.ticker != template.ticker:
        raise ValueError("Expansion company probe frontier/template ticker mismatch")
    corp = client.resolve_stock_codes([frontier.ticker])[frontier.ticker]
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    results: list[HistoricalExpansionCompanyProbePeriodResult] = []

    for candidate in frontier.candidates:
        period_root = root / candidate.period_id
        period_root.mkdir(parents=True, exist_ok=True)
        try:
            batch = client.financial_statements(
                corp,
                business_year=candidate.period_end.year,
                report_code=candidate.company_profitability_report_code,
                fs_div=template.fs_div,
            )
            raw_payload = batch.raw_payload
            raw_path = period_root / (
                captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__raw_payload.json"
            )
            raw_path.write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            observation = extract_expansion_company_profitability_observation(
                candidate,
                raw_payload,
                revenue_account_ids=template.revenue_account_ids,
                cost_of_sales_account_ids=template.cost_of_sales_account_ids,
                gross_profit_account_ids=template.gross_profit_account_ids,
            )
            if observation.available_date > evaluation_date:
                raise ValueError("Expansion company profitability uses future filing data")
            results.append(
                HistoricalExpansionCompanyProbePeriodResult(
                    period_id=candidate.period_id,
                    success=True,
                    observation=observation,
                    raw_payload_path=str(raw_path.resolve()),
                    error_type=None,
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                HistoricalExpansionCompanyProbePeriodResult(
                    period_id=candidate.period_id,
                    success=False,
                    observation=None,
                    raw_payload_path=None,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )

    report = {
        "status": "skhynix_historical_expansion_company_profitability_probe_completed",
        "evaluation_date": evaluation_date.isoformat(),
        "captured_at": captured_at.isoformat(),
        "frontier_evidence_id": frontier.evidence_id,
        "results": [asdict(item) for item in results],
        "frontier_promoted": False,
        "training_row_promoted": False,
        "fit_enabled": False,
    }
    pointer = root / "latest_company_profitability_probe.json"
    temporary = root / ".latest_company_profitability_probe.json.tmp"
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(pointer)
    return tuple(results)


__all__ = [
    "DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT",
    "HistoricalExpansionCompanyProbePeriodResult",
    "HistoricalExpansionCompanyProfitabilityObservation",
    "extract_expansion_company_profitability_observation",
    "run_expansion_company_profitability_probe",
]
