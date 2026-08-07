"""Deterministic, fail-closed metrics from selected OpenDART filing bodies."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

BODY_METRICS_SCHEMA_VERSION = 1

_EARNINGS_HEADING = re.compile(
    r"연결재무제표\s*기준\s*영업\s*\(잠정\)\s*실적\s*\(공정공시\)",
)
_CAPEX_HEADING = re.compile(r"신규\s*시설투자\s*등")
_NUMBER = r"(?:-?\d[\d,]*(?:\.\d+)?|-)"
_DATE = r"(?:\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?)"
_UNIT_SCALES: dict[str, int] = {
    "원": 1,
    "천원": 1_000,
    "백만원": 1_000_000,
    "억원": 100_000_000,
    "조원": 1_000_000_000_000,
}


def _last_section(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = list(pattern.finditer(text))
    return text[matches[-1].start() :] if matches else None


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _canonical_number(value: str) -> str | None:
    text = value.strip().replace(",", "")
    if text == "-":
        return None
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        return None
    if not numeric.is_finite():
        return None
    return format(numeric, "f")


def _scaled_krw(value: str | None, scale: int | None) -> int | None:
    if value is None or scale is None:
        return None
    try:
        scaled = Decimal(value) * scale
    except InvalidOperation:
        return None
    if scaled != scaled.to_integral_value():
        return None
    return int(scaled)


def _date_value(value: str | None) -> str | None:
    if value is None:
        return None
    numbers = re.findall(r"\d+", value)
    if len(numbers) != 3:
        return None
    year, month, day = (int(item) for item in numbers)
    if year < 2000 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _unit(section: str) -> tuple[str | None, int | None]:
    match = re.search(r"단위\s*:\s*([^\n]{1,30}?)\s+구분", section)
    if match is None:
        return None, None
    raw = re.sub(r"\s+", "", match.group(1)).replace(",%", "").replace("%", "")
    for name, scale in _UNIT_SCALES.items():
        if name in raw:
            return name, scale
    return raw or None, None


def _earnings_row(section: str, label: str) -> dict[str, object] | None:
    transition = r"(?:흑자전환|적자전환|-)"
    pattern = re.compile(
        rf"{re.escape(label)}\s+당해실적\s+({_NUMBER})\s+({_NUMBER})\s+"
        rf"({_NUMBER})\s+{transition}\s+({_NUMBER})\s+({_NUMBER})\s+{transition}"
    )
    match = pattern.search(section)
    if match is None:
        return None
    current, previous, qoq, prior_year, yoy = (
        _canonical_number(match.group(index)) for index in range(1, 6)
    )
    return {
        "current": current,
        "previous_quarter": previous,
        "qoq_pct": qoq,
        "prior_year": prior_year,
        "yoy_pct": yoy,
    }


def _parse_earnings(text: str) -> dict[str, object]:
    raw_section = _last_section(text, _EARNINGS_HEADING)
    if raw_section is None:
        return {
            "schema_version": BODY_METRICS_SCHEMA_VERSION,
            "type": "earnings_preliminary",
            "status": "unparsed",
            "reason": "full_earnings_table_heading_not_found",
        }
    section = _compact(raw_section)
    unit, scale = _unit(raw_section)
    rows: dict[str, dict[str, object]] = {}
    for key, label in (
        ("sales", "매출액"),
        ("operating_profit", "영업이익"),
        ("net_income", "당기순이익"),
    ):
        parsed = _earnings_row(section, label)
        if parsed is None:
            continue
        parsed["current_krw"] = _scaled_krw(
            parsed.get("current") if isinstance(parsed.get("current"), str) else None,
            scale,
        )
        parsed["previous_quarter_krw"] = _scaled_krw(
            (
                parsed.get("previous_quarter")
                if isinstance(parsed.get("previous_quarter"), str)
                else None
            ),
            scale,
        )
        parsed["prior_year_krw"] = _scaled_krw(
            parsed.get("prior_year") if isinstance(parsed.get("prior_year"), str) else None,
            scale,
        )
        rows[key] = parsed

    verified = (
        unit in _UNIT_SCALES
        and "sales" in rows
        and "operating_profit" in rows
        and rows["sales"].get("current") is not None
        and rows["operating_profit"].get("current") is not None
    )
    status = "verified" if verified else ("partial" if rows else "unparsed")
    result: dict[str, object] = {
        "schema_version": BODY_METRICS_SCHEMA_VERSION,
        "type": "earnings_preliminary",
        "status": status,
        "unit": unit,
        "unit_scale_krw": scale,
        "metrics": rows,
    }
    if status != "verified":
        result["reason"] = (
            "required_sales_operating_profit_or_unit_missing"
            if rows
            else "standard_earnings_rows_not_found"
        )
    return result


def _capex_amount(section: str, label: str) -> int | None:
    match = re.search(rf"{re.escape(label)}\s*([0-9][0-9,]*)", section)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def _capex_ratio(section: str) -> str | None:
    match = re.search(r"자기자본대비\s*\(%\)\s*([+-]?\d+(?:\.\d+)?)", section)
    return _canonical_number(match.group(1)) if match is not None else None


def _capex_purpose(section: str) -> str | None:
    match = re.search(r"3\.\s*투자목적\s*(.*?)\s*4\.\s*투자기간", section)
    if match is None:
        return None
    value = match.group(1).strip(" -")
    return value or None


def _capex_dates(section: str) -> tuple[str | None, str | None]:
    match = re.search(
        rf"4\.\s*투자기간\s*시작일\s*({_DATE})\s*종료일\s*({_DATE})",
        section,
    )
    if match is None:
        return None, None
    return _date_value(match.group(1)), _date_value(match.group(2))


def _parse_capex(text: str) -> dict[str, object]:
    raw_section = _last_section(text, _CAPEX_HEADING)
    if raw_section is None:
        return {
            "schema_version": BODY_METRICS_SCHEMA_VERSION,
            "type": "facility_investment",
            "status": "unparsed",
            "reason": "full_capex_table_heading_not_found",
        }
    section = _compact(raw_section)
    investment = _capex_amount(section, "투자금액(원)")
    equity = _capex_amount(section, "자기자본(원)")
    ratio = _capex_ratio(section)
    purpose = _capex_purpose(section)
    start_date, end_date = _capex_dates(section)
    verified = (
        investment is not None
        and equity is not None
        and ratio is not None
        and purpose is not None
        and start_date is not None
        and end_date is not None
    )
    any_value = any(
        value is not None
        for value in (investment, equity, ratio, purpose, start_date, end_date)
    )
    result: dict[str, object] = {
        "schema_version": BODY_METRICS_SCHEMA_VERSION,
        "type": "facility_investment",
        "status": "verified" if verified else ("partial" if any_value else "unparsed"),
        "investment_amount_krw": investment,
        "equity_krw": equity,
        "equity_ratio_pct": ratio,
        "purpose": purpose,
        "start_date": start_date,
        "end_date": end_date,
    }
    if not verified:
        result["reason"] = "required_capex_fields_missing"
    return result


def parse_disclosure_body_metrics(report_name: object, text: object) -> dict[str, object]:
    """Parse only explicitly supported filing forms; never infer unsupported types."""

    report = re.sub(r"\s+", "", str(report_name)).casefold()
    body = str(text)
    if "연결재무제표기준영업(잠정)실적(공정공시)" in report:
        return _parse_earnings(body)
    if "신규시설투자등" in report or "신규시설투자" in report:
        return _parse_capex(body)
    return {
        "schema_version": BODY_METRICS_SCHEMA_VERSION,
        "type": "unsupported",
        "status": "unsupported_report_type",
    }


__all__ = ["BODY_METRICS_SCHEMA_VERSION", "parse_disclosure_body_metrics"]
