"""Extended filing-body metrics with narrow corporate-action support."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics as _parse_base_body_metrics,
)
from alpha_cycle.intelligence.disclosure_corporate_action_metrics import (
    parse_corporate_action_body_metrics,
)


def parse_disclosure_body_metrics(report_name: object, text: object) -> dict[str, object]:
    """Parse supported corporate actions first, then the existing base forms."""

    corporate = parse_corporate_action_body_metrics(report_name, text)
    if corporate is not None:
        return corporate
    return _parse_base_body_metrics(report_name, text)


__all__ = ["parse_disclosure_body_metrics"]
