"""Focused diagnostics tests for correction parent-resolution provenance."""

from __future__ import annotations

import json

from alpha_cycle.correction_delta_diagnostics_cli import _delta_detail


def test_delta_detail_exposes_body_parent_and_heuristic_parent_separately() -> None:
    payload = json.dumps(
        {
            "status": "verified",
            "verified_field_count": 2,
            "changed_field_count": 2,
            "parent_rcept_no": "20260407800002",
            "parent_resolution_source": "body_target_submission_date",
            "parent_target_submission_date": "2026-04-07",
            "heuristic_parent_rcept_no": "20260430800083",
            "fields": [
                {
                    "field": "sales",
                    "before_matches_parent": True,
                    "after_matches_current": True,
                },
                {
                    "field": "operating_profit",
                    "before_matches_parent": True,
                    "after_matches_current": True,
                },
            ],
        }
    )

    detail = _delta_detail(payload)

    assert detail == (
        2,
        2,
        "",
        "20260407800002",
        "body_target_submission_date",
        "2026-04-07",
        "20260430800083",
    )
