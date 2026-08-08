"""Deterministic metrics for selected OpenDART corporate-action filing bodies.

Only compact, table-shaped decision filings with stable labels are supported here.
The parser always reads the final form section, never the correction-summary header,
and fails closed when required fields are missing.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

BODY_METRICS_SCHEMA_VERSION = 1
_NUMBER = r"(?:-?\d[\d,]*(?:\.\d+)?|-)"
_DATE = r"(?:\d{4}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?)"

_EQUITY_HEADING = re.compile(r"유상\s*증자\s*결정")
_DR_HEADING = re.compile(r"증권\s*예탁\s*증권\s*\(DR\)\s*발행\s*결정", re.IGNORECASE)
_OVERSEAS_LISTING_HEADING = re.compile(r"해외\s*증권시장\s*주권등\s*상장\s*결정")


def _compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _last_section(text: object, heading: re.Pattern[str]) -> str | None:
    body = str(text)
    matches = list(heading.finditer(body))
    return _compact(body[matches[-1].start() :]) if matches else None


def _bounded(
    section: str,
    start: str,
    end: str | None,
) -> str | None:
    start_match = re.search(start, section)
    if start_match is None:
        return None
    if end is None:
        return section[start_match.end() :]
    end_match = re.search(end, section[start_match.end() :])
    if end_match is None:
        return None
    end_index = start_match.end() + end_match.start()
    return section[start_match.end() : end_index]


def _canonical_number(value: str) -> str | None:
    text = value.strip().replace(",", "")
    if text == "-":
        return None
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        return None
    return format(numeric, "f") if numeric.is_finite() else None


def _integer_after(section: str | None, label: str) -> int | None:
    if section is None:
        return None
    match = re.search(rf"{label}\s*({_NUMBER})", section)
    if match is None:
        return None
    value = _canonical_number(match.group(1))
    if value is None:
        return None
    try:
        numeric = Decimal(value)
    except InvalidOperation:
        return None
    if numeric != numeric.to_integral_value():
        return None
    return int(numeric)


def _decimal_after(section: str | None, label: str) -> str | None:
    if section is None:
        return None
    match = re.search(rf"{label}\s*({_NUMBER})", section)
    return _canonical_number(match.group(1)) if match is not None else None


def _text_after(section: str | None, label: str) -> str | None:
    if section is None:
        return None
    match = re.search(rf"{label}\s*(.+)", section)
    if match is None:
        return None
    value = match.group(1).strip(" -")
    return value or None


def _date_after(section: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*({_DATE})", section)
    if match is None:
        return None
    parts = [int(item) for item in re.findall(r"\d+", match.group(1))]
    if len(parts) != 3:
        return None
    year, month, day = parts
    if year < 2000 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _result(
    metric_type: str,
    values: dict[str, object],
    required: tuple[str, ...],
) -> dict[str, object]:
    present = [name for name in required if values.get(name) is not None]
    if len(present) == len(required):
        status = "verified"
    elif any(value is not None for value in values.values()):
        status = "partial"
    else:
        status = "unparsed"
    payload: dict[str, object] = {
        "schema_version": BODY_METRICS_SCHEMA_VERSION,
        "type": metric_type,
        "status": status,
        **values,
    }
    if status != "verified":
        payload["reason"] = f"required_{metric_type}_fields_missing"
    return payload


def _parse_equity_issuance(text: object) -> dict[str, object]:
    section = _last_section(text, _EQUITY_HEADING)
    if section is None:
        return _result("equity_issuance", {}, ("common_shares_issued",))

    new_shares = _bounded(
        section,
        r"1\.\s*신주의\s*종류와\s*수",
        r"2\.\s*1주당\s*액면가액",
    )
    pre_issue = _bounded(
        section,
        r"3\.\s*증자전\s*발행주식총수\s*\(주\)",
        r"4\.\s*자금조달의\s*목적",
    )
    funding = _bounded(
        section,
        r"4\.\s*자금조달의\s*목적",
        r"5\.\s*증자방식",
    )
    method = _bounded(section, r"5\.\s*증자방식", r"6\.\s*신주\s*발행가액")
    issue_price = _bounded(
        section,
        r"6\.\s*신주\s*발행가액",
        r"7\.\s*기준주가",
    )
    reference_price = _bounded(
        section,
        r"7\.\s*기준주가",
        r"7-1\.\s*기준주가\s*산정방법",
    )
    premium = _bounded(
        section,
        r"7-2\.\s*기준주가에\s*대한\s*할인율\s*또는\s*할증율\s*\(%\)",
        r"7-3\.",
    )
    values: dict[str, object] = {
        "common_shares_issued": _integer_after(new_shares, r"보통주식\s*\(주\)"),
        "pre_issue_common_shares": _integer_after(
            pre_issue,
            r"보통주식\s*\(주\)",
        ),
        "facility_funding_krw": _integer_after(funding, r"시설자금\s*\(원\)"),
        "issuance_method": _text_after(method, r""),
        "issue_price_krw": _integer_after(issue_price, r"보통주식\s*\(원\)"),
        "reference_price_krw": _integer_after(
            reference_price,
            r"보통주식\s*\(원\)",
        ),
        "premium_discount_pct": _decimal_after(premium, r""),
        "payment_date": _date_after(section, r"9\.\s*납입일"),
        "listing_date": _date_after(section, r"12\.\s*신주의\s*상장\s*예정일"),
    }
    return _result(
        "equity_issuance",
        values,
        (
            "common_shares_issued",
            "pre_issue_common_shares",
            "facility_funding_krw",
            "issuance_method",
            "issue_price_krw",
        ),
    )


def _parse_dr_issuance(text: object) -> dict[str, object]:
    section = _last_section(text, _DR_HEADING)
    if section is None:
        return _result("depositary_receipt_issuance", {}, ("dr_total_krw",))

    total = _bounded(section, r"2\.\s*DR\s*발행총액", r"3\.\s*신주DR의\s*경우")
    issue_price = _bounded(
        section,
        r"3\.\s*신주DR의\s*경우\s*신주\s*발행가액\s*\(원\)",
        r"4\.\s*1\s*DR당\s*발행가액",
    )
    dr_price = _bounded(
        section,
        r"4\.\s*1\s*DR당\s*발행가액\s*\(통화단위\)",
        r"5\.\s*1\s*DR당\s*원주\s*전환비율",
    )
    conversion = _bounded(
        section,
        r"5\.\s*1\s*DR당\s*원주\s*전환비율\s*\(주\)",
        r"6\.\s*발행국가",
    )
    funding = _bounded(
        section,
        r"7\.\s*자금조달의\s*목적",
        r"8\.\s*청약일",
    )
    currency_match = re.search(r"\b([A-Z]{3})/1DR\b", dr_price or "")
    values: dict[str, object] = {
        "dr_total_krw": _integer_after(total, r"원화금액\s*\(원\)"),
        "share_issue_price_krw": _integer_after(
            issue_price,
            r"보통주식",
        ),
        "dr_price": _decimal_after(dr_price, r""),
        "dr_price_currency": currency_match.group(1) if currency_match is not None else None,
        "original_share_per_dr": _decimal_after(conversion, r""),
        "facility_funding_krw": _integer_after(funding, r"시설자금\s*\(원\)"),
        "subscription_date": _date_after(section, r"8\.\s*청약일"),
        "payment_date": _date_after(section, r"9\.\s*납입일"),
        "overseas_listing_date": _date_after(section, r"상장예정일"),
        "new_share_listing_date": _date_after(
            section,
            r"11\.\s*신주DR의\s*경우\s*신주상장예정일",
        ),
    }
    return _result(
        "depositary_receipt_issuance",
        values,
        (
            "dr_total_krw",
            "share_issue_price_krw",
            "dr_price",
            "original_share_per_dr",
            "facility_funding_krw",
        ),
    )


def _parse_overseas_listing(text: object) -> dict[str, object]:
    section = _last_section(text, _OVERSEAS_LISTING_HEADING)
    if section is None:
        return _result("overseas_listing", {}, ("common_shares_to_list",))

    listing = _bounded(
        section,
        r"1\.\s*상장예정주식\s*종류[ㆍ·]?수\s*\(주\)",
        r"2\.\s*공모방법",
    )
    pre_issue = _bounded(
        listing or "",
        r"발행주식\s*총수\s*\(주\)",
        None,
    )
    offering = _bounded(section, r"2\.\s*공모방법", r"3\.\s*자금조달")
    securities = _bounded(section, r"4\.\s*상장증권", r"5\.\s*상장거래소")
    exchange = _bounded(section, r"5\.\s*상장거래소\s*\(소재국가\)", r"6\.\s*해외상장목적")
    purpose = _bounded(section, r"6\.\s*해외상장목적", r"7\.\s*상장예정일자")
    listing_without_pre = (
        listing[: listing.find("발행주식 총수")]
        if listing is not None and "발행주식 총수" in listing
        else listing
    )
    values: dict[str, object] = {
        "common_shares_to_list": _integer_after(
            listing_without_pre,
            r"보통주식",
        ),
        "pre_issue_common_shares": _integer_after(pre_issue, r"보통주식"),
        "new_shares": _integer_after(offering, r"신주발행\s*\(주\)"),
        "dr_shares": _integer_after(securities, r"DR상장\s*\(주\)"),
        "exchange": _text_after(exchange, r""),
        "listing_purpose": _text_after(purpose, r""),
        "listing_date": _date_after(section, r"7\.\s*상장예정일자"),
    }
    return _result(
        "overseas_listing",
        values,
        (
            "common_shares_to_list",
            "pre_issue_common_shares",
            "new_shares",
            "dr_shares",
            "exchange",
            "listing_purpose",
            "listing_date",
        ),
    )


def parse_corporate_action_body_metrics(
    report_name: object,
    text: object,
) -> dict[str, object] | None:
    """Return supported corporate-action metrics, or None for unsupported forms."""

    report = re.sub(r"\s+", "", str(report_name)).casefold()
    if "증권예탁증권(dr)발행결정" in report:
        return _parse_dr_issuance(text)
    if "해외증권시장주권등상장결정" in report:
        return _parse_overseas_listing(text)
    if "유상증자결정" in report:
        return _parse_equity_issuance(text)
    return None


__all__ = ["BODY_METRICS_SCHEMA_VERSION", "parse_corporate_action_body_metrics"]
