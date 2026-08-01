"""Read-only OpenDART share-count and multi-period financial evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

import pandas as pd

from alpha_cycle.providers.opendart import (
    NO_DATA_STATUS,
    REPORT_PERIODS,
    CorpCode,
    OpenDartReadOnlyClient,
    normalize_listed_stock_code,
)

STOCK_TOTAL_COLUMNS = (
    "ticker",
    "corp_code",
    "corp_name",
    "business_year",
    "report_code",
    "period_end",
    "available_date",
    "receipt_no",
    "security_name",
    "security_class",
    "authorized_shares",
    "shares_issued_to_date",
    "shares_reduced_to_date",
    "issued_shares",
    "treasury_shares",
    "floating_shares",
    "normalization_warning",
)

_MISSING_INTEGER_MARKERS = frozenset(
    {
        "",
        "-",
        "--",
        "–",
        "—",
        "−",
        "none",
        "null",
        "nan",
        "n/a",
        "na",
        "해당사항없음",
        "해당없음",
        "없음",
    }
)
_WHOLE_SHARE_PATTERN = re.compile(r"^\+?[0-9]+(?:\.0+)?$")
_LEGACY_NOTE_PATTERN = re.compile(r"[가-힣]|[A-Za-z]{2,}")


@dataclass(frozen=True)
class StockTotalsBatch:
    frame: pd.DataFrame
    raw_payload: object
    corp: CorpCode
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinancialPeriodPayload:
    ticker: str
    corp_code: str
    business_year: int
    report_code: str
    period_end: date
    available_date: date
    payload: Mapping[str, object]


def _integer(value: object, field: str, *, optional: bool = True) -> int | None:
    """Parse OpenDART whole-share counts without accepting ambiguous quantities."""

    if value is None:
        text = ""
    else:
        text = "".join(str(value).strip().split()).replace(",", "")
    if text.endswith("주"):
        text = text[:-1]
    normalized = text.casefold()
    if normalized in _MISSING_INTEGER_MARKERS:
        if optional:
            return None
        raise ValueError(f"OpenDART {field} is required")
    if not _WHOLE_SHARE_PATTERN.fullmatch(text):
        raise ValueError(
            f"OpenDART {field} must be a non-negative whole-share count; value={text!r}"
        )
    try:
        decimal_value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            f"OpenDART {field} must be a non-negative whole-share count; value={text!r}"
        ) from exc
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        raise ValueError(
            f"OpenDART {field} must be a non-negative whole-share count; value={text!r}"
        )
    result = int(decimal_value)
    if result < 0:
        raise ValueError(f"OpenDART {field} cannot be negative; value={text!r}")
    return result


def _optional_integer_with_warning(
    value: object,
    field: str,
    *,
    ticker: str,
    security_name: str,
    warnings: list[str],
) -> int | None:
    """Quarantine narrative legacy notes from non-critical optional count fields."""

    try:
        return _integer(value, field)
    except ValueError:
        raw_text = "" if value is None else " ".join(str(value).strip().split())
        if not _LEGACY_NOTE_PATTERN.search(raw_text):
            raise
        sanitized = raw_text[:180]
        warning = (
            f"{ticker}:{security_name}:{field}: non-numeric legacy note normalized to "
            f"missing; value={sanitized!r}"
        )
        warnings.append(warning)
        return None


def _date_yyyymmdd(value: object, field: str) -> date:
    try:
        return datetime.strptime(str(value).strip(), "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError(f"OpenDART {field} must use YYYYMMDD") from exc


def _date_iso(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"OpenDART {field} must use YYYY-MM-DD") from exc


def _security_class(value: object) -> str:
    text = str(value).strip().casefold().replace(" ", "")
    if "보통" in text or "common" in text:
        return "common"
    if "우선" in text or "preferred" in text:
        return "preferred"
    if "합계" in text or text in {"total", "계"}:
        return "total"
    if "비고" in text or "note" in text:
        return "note"
    return "other"


def _period_end(business_year: int, report_code: str) -> date:
    if report_code not in REPORT_PERIODS:
        raise ValueError("OpenDART report_code is unsupported")
    _, month, day = REPORT_PERIODS[report_code]
    return date(business_year, month, day)


def _candidate_periods(
    evaluation_date: date,
    history_years: int,
) -> tuple[tuple[int, str], ...]:
    if history_years <= 0:
        raise ValueError("history_years must be positive")
    first_year = max(2015, evaluation_date.year - history_years + 1)
    periods: list[tuple[date, int, str]] = []
    for year in range(first_year, evaluation_date.year + 1):
        for report_code in REPORT_PERIODS:
            period_end = _period_end(year, report_code)
            if period_end <= evaluation_date:
                periods.append((period_end, year, report_code))
    periods.sort(reverse=True)
    return tuple((year, report_code) for _, year, report_code in periods)


def _visible_receipt_date(rows: list[Mapping[str, object]]) -> date | None:
    dates: list[date] = []
    for raw in rows:
        receipt_no = str(raw.get("rcept_no", "")).strip()
        if len(receipt_no) != 14 or not receipt_no.isdigit():
            raise ValueError("OpenDART receipt number must be 14 digits")
        dates.append(_date_yyyymmdd(receipt_no[:8], "rcept_no date"))
    return max(dates) if dates else None


class OpenDartValuationClient(OpenDartReadOnlyClient):
    """Official GET-only client for share counts and financial-history evidence."""

    def stock_totals(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
    ) -> StockTotalsBatch:
        period_end = _period_end(business_year, report_code)
        payload = self._json_get(
            "/api/stockTotqySttus.json",
            {
                "corp_code": corp.corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
            },
            allow_no_data=True,
        )
        if str(payload.get("status", "")).strip() == NO_DATA_STATUS:
            return StockTotalsBatch(
                pd.DataFrame(columns=STOCK_TOTAL_COLUMNS),
                dict(payload),
                corp,
            )
        raw_rows = payload.get("list", [])
        if not isinstance(raw_rows, list):
            raise ValueError("OpenDART stock-total list must be an array")
        records: list[dict[str, object]] = []
        batch_warnings: list[str] = []
        for raw_value in raw_rows:
            if not isinstance(raw_value, dict):
                raise ValueError("OpenDART stock-total row must be an object")
            raw = cast(Mapping[str, object], raw_value)
            row_corp_code = str(raw.get("corp_code", "")).strip()
            if row_corp_code and row_corp_code != corp.corp_code:
                raise ValueError("OpenDART stock-total corp_code does not match the request")
            receipt_no = str(raw.get("rcept_no", "")).strip()
            if len(receipt_no) != 14 or not receipt_no.isdigit():
                raise ValueError("OpenDART stock-total receipt number must be 14 digits")
            available_date = _date_yyyymmdd(receipt_no[:8], "rcept_no date")
            settlement_date = _date_iso(raw.get("stlm_dt", ""), "stlm_dt")
            if settlement_date != period_end:
                raise ValueError(
                    "OpenDART stock-total settlement date does not match requested period: "
                    f"expected={period_end}, actual={settlement_date}"
                )
            security_name = str(raw.get("se", "")).strip()
            if not security_name:
                raise ValueError("OpenDART stock-total security name is required")
            row_warnings: list[str] = []
            authorized_shares = _optional_integer_with_warning(
                raw.get("isu_stock_totqy"),
                "isu_stock_totqy",
                ticker=corp.stock_code,
                security_name=security_name,
                warnings=row_warnings,
            )
            shares_issued_to_date = _optional_integer_with_warning(
                raw.get("now_to_isu_stock_totqy"),
                "now_to_isu_stock_totqy",
                ticker=corp.stock_code,
                security_name=security_name,
                warnings=row_warnings,
            )
            shares_reduced_to_date = _optional_integer_with_warning(
                raw.get("now_to_dcrs_stock_totqy"),
                "now_to_dcrs_stock_totqy",
                ticker=corp.stock_code,
                security_name=security_name,
                warnings=row_warnings,
            )
            issued_shares = _integer(
                raw.get("istc_totqy"),
                "istc_totqy",
                optional=False,
            )
            treasury_shares = _optional_integer_with_warning(
                raw.get("tesstk_co"),
                "tesstk_co",
                ticker=corp.stock_code,
                security_name=security_name,
                warnings=row_warnings,
            )
            floating_shares = _optional_integer_with_warning(
                raw.get("distb_stock_co"),
                "distb_stock_co",
                ticker=corp.stock_code,
                security_name=security_name,
                warnings=row_warnings,
            )
            batch_warnings.extend(row_warnings)
            records.append(
                {
                    "ticker": corp.stock_code,
                    "corp_code": corp.corp_code,
                    "corp_name": str(raw.get("corp_name", corp.corp_name)).strip(),
                    "business_year": business_year,
                    "report_code": report_code,
                    "period_end": period_end,
                    "available_date": available_date,
                    "receipt_no": receipt_no,
                    "security_name": security_name,
                    "security_class": _security_class(security_name),
                    "authorized_shares": authorized_shares,
                    "shares_issued_to_date": shares_issued_to_date,
                    "shares_reduced_to_date": shares_reduced_to_date,
                    "issued_shares": issued_shares,
                    "treasury_shares": treasury_shares,
                    "floating_shares": floating_shares,
                    "normalization_warning": " | ".join(row_warnings) or None,
                }
            )
        frame = pd.DataFrame(records, columns=STOCK_TOTAL_COLUMNS)
        if frame.empty:
            raise ValueError("OpenDART stock-total response contains no rows")
        if frame.duplicated(["security_class", "security_name"]).any():
            raise ValueError("OpenDART stock-total response contains duplicate security rows")
        diagnostic_payload = dict(payload)
        diagnostic_payload["_normalization_warnings"] = list(batch_warnings)
        return StockTotalsBatch(
            frame.sort_values(
                ["security_class", "security_name"],
                kind="stable",
            ).reset_index(drop=True),
            diagnostic_payload,
            corp,
            tuple(batch_warnings),
        )

    def latest_stock_totals(
        self,
        corp: CorpCode,
        *,
        evaluation_date: date,
    ) -> StockTotalsBatch:
        attempts: list[dict[str, object]] = []
        for business_year, report_code in _candidate_periods(evaluation_date, 2):
            batch = self.stock_totals(
                corp,
                business_year=business_year,
                report_code=report_code,
            )
            attempts.append(
                {
                    "business_year": business_year,
                    "report_code": report_code,
                    "raw_payload": batch.raw_payload,
                }
            )
            if batch.frame.empty:
                continue
            visible = batch.frame.loc[
                (batch.frame["period_end"] <= evaluation_date)
                & (batch.frame["available_date"] <= evaluation_date)
            ].copy()
            if not visible.empty:
                return StockTotalsBatch(
                    visible.reset_index(drop=True),
                    {"selected": batch.raw_payload, "attempts": attempts},
                    corp,
                    batch.warnings,
                )
        raise ValueError(
            f"No OpenDART stock totals were available by {evaluation_date} "
            f"for {corp.stock_code}"
        )

    def financial_period_payload(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
        fs_div: str = "CFS",
        evaluation_date: date,
    ) -> FinancialPeriodPayload | None:
        period_end = _period_end(business_year, report_code)
        if period_end > evaluation_date:
            return None
        if fs_div not in {"CFS", "OFS"}:
            raise ValueError("OpenDART fs_div must be CFS or OFS")
        payload = self._json_get(
            "/api/fnlttSinglAcntAll.json",
            {
                "corp_code": corp.corp_code,
                "bsns_year": str(business_year),
                "reprt_code": report_code,
                "fs_div": fs_div,
            },
            allow_no_data=True,
        )
        if str(payload.get("status", "")).strip() == NO_DATA_STATUS:
            return None
        raw_rows = payload.get("list", [])
        if not isinstance(raw_rows, list):
            raise ValueError("OpenDART financial-history list must be an array")
        rows = [
            cast(Mapping[str, object], raw)
            for raw in raw_rows
            if isinstance(raw, dict)
        ]
        if len(rows) != len(raw_rows):
            raise ValueError("OpenDART financial-history rows must be objects")
        available_date = _visible_receipt_date(rows)
        if available_date is None or available_date > evaluation_date:
            return None
        visible_rows: list[dict[str, object]] = []
        for raw in rows:
            row_corp = str(raw.get("corp_code", "")).strip()
            if row_corp and row_corp != corp.corp_code:
                raise ValueError("OpenDART financial-history corp_code does not match request")
            row_stock = str(raw.get("stock_code", "")).strip()
            if row_stock and normalize_listed_stock_code(row_stock) != corp.stock_code:
                raise ValueError("OpenDART financial-history stock_code does not match request")
            if str(raw.get("bsns_year", business_year)).strip() != str(business_year):
                raise ValueError("OpenDART financial-history business year does not match request")
            if str(raw.get("reprt_code", report_code)).strip() != report_code:
                raise ValueError("OpenDART financial-history report code does not match request")
            visible_rows.append(dict(raw))
        visible_payload = dict(payload)
        visible_payload["list"] = visible_rows
        return FinancialPeriodPayload(
            ticker=corp.stock_code,
            corp_code=corp.corp_code,
            business_year=business_year,
            report_code=report_code,
            period_end=period_end,
            available_date=available_date,
            payload=visible_payload,
        )

    def financial_history_payloads(
        self,
        corp: CorpCode,
        *,
        evaluation_date: date,
        history_years: int,
        fs_div: str = "CFS",
    ) -> tuple[FinancialPeriodPayload, ...]:
        result: list[FinancialPeriodPayload] = []
        for business_year, report_code in reversed(
            _candidate_periods(evaluation_date, history_years)
        ):
            period = self.financial_period_payload(
                corp,
                business_year=business_year,
                report_code=report_code,
                fs_div=fs_div,
                evaluation_date=evaluation_date,
            )
            if period is not None:
                result.append(period)
        if not result:
            raise ValueError(
                f"No OpenDART financial history was available for {corp.stock_code}"
            )
        return tuple(result)


__all__ = [
    "FinancialPeriodPayload",
    "OpenDartValuationClient",
    "StockTotalsBatch",
]
