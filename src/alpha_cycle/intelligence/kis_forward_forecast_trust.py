"""Trust boundary for KIS estimate-perform forecast columns.

Historical crosschecks currently verify a narrow claim: selected output2 rows and their
scale match OpenDART actual financials for 005930/000660 over 2023-2025. They do not
establish that output4.dt maps positionally onto output2.dataN for forecast columns, nor
that the historical scale continues unchanged into those forecast columns.

Until those two forecast-specific claims are authoritatively certified, numeric forward
levels, growth rates, margins, and snapshot revisions must remain ineligible for decision
evidence.
"""

from __future__ import annotations

FORECAST_COLUMN_PERIOD_ALIGNMENT_CERTIFIED = False
FORECAST_SCALE_CONTINUITY_CERTIFIED = False
FORWARD_NUMERIC_EVIDENCE_ELIGIBLE = (
    FORECAST_COLUMN_PERIOD_ALIGNMENT_CERTIFIED
    and FORECAST_SCALE_CONTINUITY_CERTIFIED
)
FORWARD_BLOCK_REASON = "forecast_column_period_and_scale_semantics_not_certified"


def require_forward_numeric_evidence_eligible() -> None:
    """Fail closed before interpreting KIS forecast DATA columns numerically."""

    if not FORWARD_NUMERIC_EVIDENCE_ELIGIBLE:
        raise ValueError(
            "KIS forward numeric evidence is blocked: historical row/scale semantics are "
            "crosschecked, but forecast DATA-column-to-period alignment and forecast scale "
            "continuity are not authoritatively certified"
        )


__all__ = [
    "FORECAST_COLUMN_PERIOD_ALIGNMENT_CERTIFIED",
    "FORECAST_SCALE_CONTINUITY_CERTIFIED",
    "FORWARD_BLOCK_REASON",
    "FORWARD_NUMERIC_EVIDENCE_ELIGIBLE",
    "require_forward_numeric_evidence_eligible",
]
