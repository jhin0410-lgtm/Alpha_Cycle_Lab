"""Focused tests for correction body-metric parse reason diagnostics."""

from __future__ import annotations

import json

from alpha_cycle.correction_delta_diagnostics_cli import _body_metrics_reason


def test_body_metrics_reason_is_extracted_without_exposing_body_text() -> None:
    payload = json.dumps(
        {
            "schema_version": 1,
            "type": "earnings_preliminary",
            "status": "unparsed",
            "reason": "standard_earnings_rows_not_found",
        }
    )

    assert _body_metrics_reason(payload) == "standard_earnings_rows_not_found"
    assert _body_metrics_reason("") == ""
