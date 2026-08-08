"""Supported correction-header deltas for selected corporate-action forms."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = r"(?:-?\d[\d,]*(?:\.\d+)?|-)"


def _canonical_number(value: str) -> str | None:
    text = value.strip().replace(",", "")
    if text == "-":
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return format(number, "f") if number.is_finite() else None


def _correction_summary(text: object, final_heading: re.Pattern[str]) -> str | None:
    body = str(text)
    marker = re.search(r"정정\s*(?:사항|항목).*?정정\s*전.*?정정\s*후", body, re.DOTALL)
    if marker is None:
        return None
    headings = [match for match in final_heading.finditer(body) if match.start() > marker.end()]
    end = headings[-1].start() if headings else len(body)
    if end <= marker.end():
        return None
    return re.sub(r"\s+", " ", body[marker.end() : end]).strip()


def _between(section: str, start: str, end: str | None) -> str | None:
    start_match = re.search(start, section)
    if start_match is None:
        return None
    tail = section[start_match.end() :]
    if end is None:
        return tail
    end_match = re.search(end, tail)
    return tail[: end_match.start()] if end_match is not None else tail


def _two_values(block: str | None) -> tuple[object, object] | None:
    if block is None:
        return None
    tokens = re.findall(_NUMBER, block)
    values = [_canonical_number(token) for token in tokens]
    if len(values) < 2:
        return None
    return values[-2], values[-1]


def _integer_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return int(number)


def _row(field: str, values: tuple[object, object], *, integer: bool) -> dict[str, object]:
    before_raw, after_raw = values
    if integer:
        before: object = _integer_or_none(before_raw)
        after: object = _integer_or_none(after_raw)
    else:
        before = before_raw
        after = after_raw
    return {
        "field": field,
        "before": before,
        "after": after,
        "changed": before != after,
    }


def _equity_rows(text: object) -> list[dict[str, object]]:
    section = _correction_summary(text, re.compile(r"유상\s*증자\s*결정"))
    if section is None:
        return []
    definitions = (
        (
            "facility_funding_krw",
            r"4\.\s*자금조달의\s*목적\s*-?\s*시설자금\s*\(원\)",
            r"6\.\s*신주\s*발행가액",
            True,
        ),
        (
            "issue_price_krw",
            r"6\.\s*신주\s*발행가액\s*-?\s*보통주식\s*\(원\)",
            r"7\.\s*기준주가",
            True,
        ),
        (
            "reference_price_krw",
            r"7\.\s*기준주가\s*-?\s*보통주식\s*\(원\)",
            r"7-2\.\s*기준주가에\s*대한",
            True,
        ),
        (
            "premium_discount_pct",
            r"7-2\.\s*기준주가에\s*대한\s*할인율\s*또는\s*할증율\s*\(%\)",
            r"20\.\s*기타\s*투자판단",
            False,
        ),
    )
    rows: list[dict[str, object]] = []
    for field, start, end, integer in definitions:
        values = _two_values(_between(section, start, end))
        if values is not None:
            rows.append(_row(field, values, integer=integer))
    return rows


def _dr_rows(text: object) -> list[dict[str, object]]:
    heading = re.compile(
        r"증권\s*예탁\s*증권\s*\(DR\)\s*발행\s*결정",
        re.IGNORECASE,
    )
    section = _correction_summary(text, heading)
    if section is None:
        return []
    definitions = (
        (
            "dr_total_krw",
            r"원화금액\s*\(원\)",
            r"3\.\s*신주DR의\s*경우",
        ),
        (
            "share_issue_price_krw",
            r"3\.\s*신주DR의\s*경우\s*신주\s*발행가액\s*\(원\).*?보통주식",
            r"4\.\s*1\s*DR당\s*발행가액",
        ),
        (
            "facility_funding_krw",
            r"7\.\s*자금조달의\s*목적.*?시설자금\s*\(원\)",
            r"(?:8\.\s*청약일|$)",
        ),
    )
    rows: list[dict[str, object]] = []
    for field, start, end in definitions:
        values = _two_values(_between(section, start, end))
        if values is not None:
            rows.append(_row(field, values, integer=True))
    return rows


def corporate_action_delta_rows(metric_type: str, text: object) -> list[dict[str, object]]:
    """Return only same-unit numeric correction fields suitable for certification."""

    if metric_type == "equity_issuance":
        return _equity_rows(text)
    if metric_type == "depositary_receipt_issuance":
        return _dr_rows(text)
    if metric_type == "overseas_listing":
        # The supported 2026-07 SK hynix correction changes narrative context only.
        # Do not manufacture a numeric delta from unchanged final-form values.
        return []
    return []


__all__ = ["corporate_action_delta_rows"]
