"""Tests for upstream disclosure correction normalization and lineage."""

from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.disclosure_provenance import (
    normalize_disclosure_tables,
)


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "rcept_no": "20260701000001",
                "report_name": "주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 1),
                "category": "financing",
                "priority": "high",
                "is_noise": False,
                "is_correction": "False",
            },
            {
                "ticker": "000660",
                "rcept_no": "20260706000002",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 6),
                "category": "financing",
                "priority": "high",
                "is_noise": False,
                "is_correction": "False",
            },
            {
                "ticker": "000660",
                "rcept_no": "20260710000003",
                "report_name": "[기재정정]주요사항보고서(유상증자결정)",
                "receipt_date": date(2026, 7, 10),
                "category": "financing",
                "priority": "high",
                "is_noise": False,
                "is_correction": "1",
            },
            {
                "ticker": "000660",
                "rcept_no": "20260729000004",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": date(2026, 7, 29),
                "category": "earnings",
                "priority": "high",
                "is_noise": False,
                "is_correction": "0",
            },
            {
                "ticker": "005930",
                "rcept_no": "20260730000005",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": date(2026, 7, 30),
                "category": "earnings",
                "priority": "high",
                "is_noise": False,
                "is_correction": None,
            },
        ]
    )


def test_title_normalization_prevents_false_like_strings_from_becoming_true() -> None:
    events, _, _, warnings = normalize_disclosure_tables(
        _events(),
        _events(),
        pd.DataFrame([{"ticker": "000660"}, {"ticker": "005930"}]),
    )
    indexed = events.set_index("rcept_no")

    assert not bool(indexed.loc["20260701000001", "is_correction"])
    assert not bool(indexed.loc["20260729000004", "is_correction"])
    assert bool(indexed.loc["20260706000002", "is_correction"])
    assert indexed.loc["20260706000002", "correction_flag_source"] == "report_name"
    assert bool(indexed.loc["20260706000002", "correction_flag_conflict"])
    assert "disclosure_correction_flag_conflicts:1" in warnings


def test_repeated_corrections_form_an_auditable_chain() -> None:
    events, catalysts, summary, warnings = normalize_disclosure_tables(
        _events(),
        _events(),
        pd.DataFrame([{"ticker": "000660"}, {"ticker": "005930"}]),
    )
    indexed = events.set_index("rcept_no")

    first = indexed.loc["20260706000002"]
    second = indexed.loc["20260710000003"]
    assert first["correction_parent_rcept_no"] == "20260701000001"
    assert first["correction_chain_root_rcept_no"] == "20260701000001"
    assert first["correction_chain_order"] == 1
    assert second["correction_parent_rcept_no"] == "20260706000002"
    assert second["correction_chain_root_rcept_no"] == "20260701000001"
    assert second["correction_chain_order"] == 2
    assert second["correction_chain_event_count"] == 3
    assert bool(second["is_latest_in_correction_chain"])
    assert not bool(first["is_latest_in_correction_chain"])

    catalyst = catalysts.set_index("rcept_no").loc["20260710000003"]
    assert catalyst["correction_chain_order"] == 2
    diagnostics = summary.set_index("ticker").loc["000660"]
    assert diagnostics["correction_disclosures"] == 2
    assert diagnostics["correction_flag_conflicts"] == 1
    assert diagnostics["orphan_corrections"] == 0
    assert "disclosure_orphan_corrections:1" in warnings


def test_unmatched_correction_is_explicitly_marked_orphan() -> None:
    events, _, summary, warnings = normalize_disclosure_tables(
        _events(),
        _events(),
        pd.DataFrame([{"ticker": "000660"}, {"ticker": "005930"}]),
    )
    samsung = events.set_index("rcept_no").loc["20260730000005"]

    assert samsung["correction_lineage_status"] == "orphan_correction"
    assert pd.isna(samsung["correction_parent_rcept_no"])
    assert samsung["correction_chain_root_rcept_no"] == "20260730000005"
    assert summary.set_index("ticker").loc["005930", "orphan_corrections"] == 1
    assert "disclosure_orphan_corrections:1" in warnings
