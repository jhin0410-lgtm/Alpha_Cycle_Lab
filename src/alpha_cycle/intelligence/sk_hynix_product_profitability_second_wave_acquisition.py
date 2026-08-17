"""Acquire the six-row 2019Q1-2020Q3 SK hynix source frontier in one pass.

Issuer cycle drivers are already exact numeric source facts from official Newsroom releases.
This module probes the two remaining source layers independently: OpenDART product revenue
and consolidated company profitability. Outputs stay isolated and never promote training
rows, fit a model, or evaluate the sealed holdout.
"""

from __future__ import annotations

import hashlib
import json
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
    HistoricalExpansionFrontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
    ProductRevenueProbePeriodResult,
    run_product_revenue_expansion_probe,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveCandidate,
    SecondWaveFrontier,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-second-wave-product-probe"
)
DEFAULT_SECOND_WAVE_COMPANY_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-second-wave-company-probe"
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
        raise ValueError(f"Second-wave company {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Second-wave company {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Second-wave company {label} must be integral KRW")
    return int(amount)


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_payload, dict):
        raise ValueError("Second-wave company raw payload must be an object")
    financials = cast(dict[object, object], raw_payload).get("financials")
    if not isinstance(financials, dict):
        raise ValueError("Second-wave company raw payload lacks financials")
    raw_rows = cast(dict[object, object], financials).get("list")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Second-wave company financial list must be a non-empty array")
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise ValueError("Second-wave company financial row must be an object")
        rows.append(
            {str(key): value for key, value in cast(dict[object, object], raw_row).items()}
        )
    return tuple(rows)


def _select_account(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    candidate: SecondWaveCandidate,
    *,
    label: str,
) -> tuple[int, str, date]:
    accepted = {item.casefold() for item in account_ids}
    matches: list[tuple[int, str, date]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(candidate.period_end.year):
            continue
        if row_code and row_code != candidate.company_profitability_report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        if len(receipt) != 14 or not receipt.isdigit():
            raise ValueError(f"Second-wave company {label} receipt is invalid")
        available_date = date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))
        matches.append((_integral_krw(row.get("thstrm_amount"), label), receipt, available_date))
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"Second-wave company account must resolve uniquely: "
            f"{candidate.period_id} {label} count={len(unique)}"
        )
    return unique[0]


@dataclass(frozen=True)
class SecondWaveCompanyObservation:
    period_id: str
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

    def __post_init__(self) -> None:
        if self.revenue_krw <= 0 or self.cost_of_sales_krw < 0:
            raise ValueError("Second-wave company amounts are invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("Second-wave company accounting identity failed")
        if len(self.raw_payload_sha256) != 64:
            raise ValueError("Second-wave company raw hash must be SHA-256")
        if (
            not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
        ):
            raise ValueError("Second-wave company observation exceeded source boundary")


@dataclass(frozen=True)
class SecondWaveCompanyResult:
    period_id: str
    success: bool
    observation: SecondWaveCompanyObservation | None
    raw_payload_path: str | None
    error_type: str | None
    error: str | None

    def __post_init__(self) -> None:
        if self.success != (self.observation is not None):
            raise ValueError("Second-wave company success state is inconsistent")
        if self.success and self.raw_payload_path is None:
            raise ValueError("Second-wave company success requires raw payload")
        if self.success and (self.error_type is not None or self.error is not None):
            raise ValueError("Second-wave company success cannot retain an error")
        if not self.success and (self.error_type is None or self.error is None):
            raise ValueError("Second-wave company failure must retain an error")


@dataclass(frozen=True)
class SecondWaveAcquisitionResult:
    period_id: str
    driver_four_field_numeric_source_certified: bool
    product_revenue_probe_success: bool
    company_profitability_verified: bool
    product_artifact_pointer: str | None
    company_observation: SecondWaveCompanyObservation | None
    product_error: str | None
    company_error: str | None
    training_row_promoted: bool = False
    fit_enabled: bool = False
    holdout_evaluation_allowed: bool = False

    @property
    def source_layer_complete(self) -> bool:
        return (
            self.driver_four_field_numeric_source_certified
            and self.product_revenue_probe_success
            and self.company_profitability_verified
        )

    def __post_init__(self) -> None:
        if self.training_row_promoted or self.fit_enabled or self.holdout_evaluation_allowed:
            raise ValueError("Second-wave acquisition exceeded isolated trust boundary")


def _run_company_probe(
    client: OpenDartReadOnlyClient,
    frontier: SecondWaveFrontier,
    *,
    evaluation_date: date,
    output: Path,
) -> tuple[SecondWaveCompanyResult, ...]:
    template = load_quarterly_company_profitability_registry(
        DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY
    )
    corp = client.resolve_stock_codes([frontier.ticker])[frontier.ticker]
    output.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC)
    results: list[SecondWaveCompanyResult] = []
    for candidate in frontier.candidates:
        raw_path: Path | None = None
        try:
            batch = client.financial_statements(
                corp,
                business_year=candidate.period_end.year,
                report_code=candidate.company_profitability_report_code,
                fs_div=template.fs_div,
            )
            raw_payload = batch.raw_payload
            period_root = output / candidate.period_id
            period_root.mkdir(parents=True, exist_ok=True)
            raw_path = period_root / (
                captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__raw_payload.json"
            )
            raw_path.write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            rows = _financial_rows(raw_payload)
            revenue, revenue_receipt, revenue_date = _select_account(
                rows, template.revenue_account_ids, candidate, label="revenue"
            )
            cost, cost_receipt, cost_date = _select_account(
                rows, template.cost_of_sales_account_ids, candidate, label="cost_of_sales"
            )
            gross, gross_receipt, gross_date = _select_account(
                rows, template.gross_profit_account_ids, candidate, label="gross_profit"
            )
            if len({revenue_receipt, cost_receipt, gross_receipt}) != 1:
                raise ValueError("Second-wave company selected accounts cross filing revisions")
            if len({revenue_date, cost_date, gross_date}) != 1:
                raise ValueError("Second-wave company selected accounts cross availability dates")
            if revenue - cost != gross:
                raise ValueError("Second-wave company direct accounting identity failed")
            available_date = revenue_date
            if available_date > evaluation_date:
                raise ValueError("Second-wave company probe uses future filing data")
            observation = SecondWaveCompanyObservation(
                period_id=candidate.period_id,
                rcept_no=revenue_receipt,
                available_date=available_date,
                revenue_krw=revenue,
                cost_of_sales_krw=cost,
                gross_profit_krw=gross,
                gross_margin_percent=gross / revenue * 100.0,
                raw_payload_sha256=_sha_payload(raw_payload),
            )
            results.append(
                SecondWaveCompanyResult(
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
                SecondWaveCompanyResult(
                    period_id=candidate.period_id,
                    success=False,
                    observation=None,
                    raw_payload_path=(
                        str(raw_path.resolve())
                        if raw_path is not None and raw_path.is_file()
                        else None
                    ),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
    pointer = output / "latest_company_probe.json"
    pointer.write_text(
        json.dumps(
            {
                "status": "skhynix_second_wave_company_probe_completed",
                "evaluation_date": evaluation_date.isoformat(),
                "frontier_evidence_id": frontier.evidence_id,
                "results": [asdict(item) for item in results],
                "training_row_promoted": False,
                "fit_enabled": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    return tuple(results)


def run_second_wave_acquisition(
    client: OpenDartReadOnlyClient,
    frontier: SecondWaveFrontier,
    *,
    evaluation_date: date,
    product_output: str | Path = DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
    company_output: str | Path = DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    product_template_registry: str | Path = DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
) -> tuple[SecondWaveAcquisitionResult, ...]:
    if evaluation_date < max(item.opendart_discovery_end_date for item in frontier.candidates):
        raise ValueError("Second-wave evaluation date predates source filing windows")
    product = run_product_revenue_expansion_probe(
        client,
        cast(HistoricalExpansionFrontier, frontier),
        evaluation_date=evaluation_date,
        output=product_output,
        template_registry=product_template_registry,
    )
    company = _run_company_probe(
        client,
        frontier,
        evaluation_date=evaluation_date,
        output=Path(company_output),
    )
    product_by_period: dict[str, ProductRevenueProbePeriodResult] = {
        item.period_id: item for item in product
    }
    company_by_period = {item.period_id: item for item in company}
    return tuple(
        SecondWaveAcquisitionResult(
            period_id=candidate.period_id,
            driver_four_field_numeric_source_certified=True,
            product_revenue_probe_success=product_by_period[candidate.period_id].success,
            company_profitability_verified=company_by_period[candidate.period_id].success,
            product_artifact_pointer=product_by_period[candidate.period_id].artifact_pointer,
            company_observation=company_by_period[candidate.period_id].observation,
            product_error=product_by_period[candidate.period_id].error,
            company_error=company_by_period[candidate.period_id].error,
        )
        for candidate in frontier.candidates
    )


__all__ = [
    "DEFAULT_SECOND_WAVE_COMPANY_OUTPUT",
    "DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT",
    "SecondWaveAcquisitionResult",
    "SecondWaveCompanyObservation",
    "SecondWaveCompanyResult",
    "run_second_wave_acquisition",
]
