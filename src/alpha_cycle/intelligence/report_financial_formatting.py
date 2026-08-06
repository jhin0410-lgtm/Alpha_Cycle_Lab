"""Human-readable financial formatting for generated Markdown reports."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import cast

import numpy as np
import pandas as pd


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _format_percentage_points(value: object) -> str:
    number = _number(value)
    return f"{number:+.1f}%p" if number is not None else "N/A"


def _format_krw(value: object) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    absolute = abs(number)
    if absolute >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:,.2f}조 원"
    if absolute >= 100_000_000:
        return f"{number / 100_000_000:,.1f}억 원"
    return f"{number:,.0f}원"


def apply_financial_report_formatting(
    report: str,
    financial_kpis: pd.DataFrame,
) -> str:
    """Format report-only financial values without changing source snapshots."""

    if financial_kpis.empty or "ticker" not in financial_kpis.columns:
        return report
    lookup = {
        str(raw["ticker"]).zfill(6): cast(Mapping[str, object], raw)
        for raw in financial_kpis.to_dict(orient="records")
    }
    lines: list[str] = []
    current_ticker: str | None = None
    for line in report.splitlines():
        if line.startswith("## "):
            heading = line.removeprefix("## ").strip()
            current_ticker = heading.zfill(6) if heading.isdigit() else None
        row = lookup.get(current_ticker or "")
        if row is not None and line.startswith("- 영업이익률 변화:"):
            line = "- 영업이익률 변화: " + _format_percentage_points(
                row.get("operating_margin_change_pp")
            )
        elif row is not None and line.startswith("- FCF:"):
            line = "- FCF: " + _format_krw(row.get("free_cash_flow"))
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["apply_financial_report_formatting"]
