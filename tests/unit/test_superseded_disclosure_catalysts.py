"""Regression tests for superseded original and correction disclosures."""

from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.disclosure_provenance import (
    normalize_disclosure_tables,
)


def test_latest_correction_replaces_original_in_catalysts() -> None:
    events = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260730800077",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": date(2026, 7, 30),
                "category": "earnings",
                "priority": "high",
                "material_score": 5,
                "is_noise": False,
                "is_correction": False,
                "is_recent": True,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260730800078",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": date(2026, 7, 30),
                "category": "earnings",
                "priority": "high",
                "material_score": 5,
                "is_noise": False,
                "is_correction": True,
                "is_recent": True,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260707800001",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": date(2026, 7, 7),
                "category": "earnings",
                "priority": "high",
                "material_score": 5,
                "is_noise": False,
                "is_correction": False,
                "is_recent": True,
            },
        ]
    )

    normalized_events, catalysts, _, _ = normalize_disclosure_tables(
        events,
        events.copy(),
        pd.DataFrame([{"ticker": "005930"}]),
    )

    event_lookup = normalized_events.set_index("rcept_no")
    assert not bool(
        event_lookup.loc["20260730800077", "is_latest_in_correction_chain"]
    )
    assert bool(
        event_lookup.loc["20260730800078", "is_latest_in_correction_chain"]
    )

    receipts = set(catalysts["rcept_no"].astype(str))
    assert "20260730800077" not in receipts
    assert "20260730800078" in receipts
    assert "20260707800001" in receipts
    assert len(catalysts) == 2


def test_repeated_corrections_leave_only_final_chain_event() -> None:
    events = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "rcept_no": "20260624000420",
                "report_name": "주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 6, 24),
                "category": "financing",
                "priority": "high",
                "material_score": 4,
                "is_noise": False,
                "is_correction": False,
                "is_recent": True,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260706000403",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 6),
                "category": "financing",
                "priority": "high",
                "material_score": 4,
                "is_noise": False,
                "is_correction": True,
                "is_recent": True,
            },
            {
                "ticker": "000660",
                "rcept_no": "20260710000404",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 10),
                "category": "financing",
                "priority": "high",
                "material_score": 4,
                "is_noise": False,
                "is_correction": True,
                "is_recent": True,
            },
        ]
    )

    _, catalysts, _, _ = normalize_disclosure_tables(
        events,
        events.copy(),
        pd.DataFrame([{"ticker": "000660"}]),
    )

    assert list(catalysts["rcept_no"].astype(str)) == ["20260710000404"]
    assert int(catalysts.iloc[0]["correction_chain_order"]) == 2
