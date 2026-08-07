"""Strict parsing for grouped-column OpenDART correction tables."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_NUMBER = r"(?:-?\d[\d,]*(?:\.\d+)?|-)"


def _canonical_number(value: str) -> str | None:
    text = value.strip().replace(",", "")
    if text == "-":
        return None
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        return None
    return format(numeric, "f") if numeric.is_finite() else None


def parse_grouped_earnings_delta_rows(section: str) -> list[dict[str, object]]:
    """Parse a grouped correction block only when its column layout is explicit.

    Some KRX/OpenDART correction tables render four earnings labels in one cell,
    followed by four `before` values in the next cell and four `after` values in
    the next cell. Plain-text normalization preserves text order but loses table
    cell boundaries. This parser accepts only the exact four-label sequence and
    exactly eight immediately following numeric values.
    """

    pattern = re.compile(
        r"매출액\s*\(당해실적\).*?"
        r"매출액\s*\(누계실적\).*?"
        r"영업이익\s*\(당해실적\).*?"
        r"영업이익\s*\(누계실적\)\s+"
        rf"({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+"
        rf"({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})(?=\s|$)"
    )
    match = pattern.search(section)
    if match is None:
        return []

    values = [_canonical_number(match.group(index)) for index in range(1, 9)]
    before_sales, _, before_operating, _, after_sales, _, after_operating, _ = values
    return [
        {
            "field": "sales",
            "before": before_sales,
            "after": after_sales,
            "changed": before_sales != after_sales,
        },
        {
            "field": "operating_profit",
            "before": before_operating,
            "after": after_operating,
            "changed": before_operating != after_operating,
        },
    ]


__all__ = ["parse_grouped_earnings_delta_rows"]
