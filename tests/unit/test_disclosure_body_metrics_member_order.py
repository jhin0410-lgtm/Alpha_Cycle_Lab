"""Regression tests for multi-member corrected earnings documents."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics,
)

_FULL_TABLE = """
연결재무제표 기준 영업(잠정)실적(공정공시)
실적기간
당기실적 2026-04-01 ~ 2026-06-30
1. 연결실적내용
단위 : 조원, %
구분 당기실적 전기실적 전기대비 전년동기실적 전년동기대비
매출액 당해실적 90.00 79.00 13.92 - 74.00 21.62 -
누계실적 169.00 - - - 145.00 16.55 -
영업이익 당해실적 15.00 12.00 25.00 - 10.00 50.00 -
누계실적 27.00 - - - 18.00 50.00 -
당기순이익 당해실적 11.00 9.00 22.22 - 8.00 37.50 -
누계실적 20.00 - - - 14.00 42.86 -
2. 정보제공내역 정보제공자 IR팀
"""

_CORRECTION_SUMMARY = """
정정신고(보고)
정정일자 2026-07-30
1. 정정관련 공시서류 연결재무제표기준영업(잠정)실적(공정공시)
4. 정정사항
정정항목 정정전 정정후
매출액(당해실적) 89.00 90.00
영업이익(당해실적) 14.00 15.00
"""


def test_verified_full_table_is_selected_when_correction_summary_member_is_last() -> None:
    body = _FULL_TABLE + "\n\n" + _CORRECTION_SUMMARY

    result = parse_disclosure_body_metrics(
        "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        body,
    )

    assert result["status"] == "verified"
    assert result["unit"] == "조원"
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["sales"]["current"] == "90.00"
    assert metrics["operating_profit"]["current"] == "15.00"


def test_conflicting_verified_full_tables_fail_closed() -> None:
    conflicting = _FULL_TABLE.replace(
        "매출액 당해실적 90.00",
        "매출액 당해실적 91.00",
        1,
    )
    body = _FULL_TABLE + "\n\n" + conflicting

    result = parse_disclosure_body_metrics(
        "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        body,
    )

    assert result == {
        "schema_version": 1,
        "type": "earnings_preliminary",
        "status": "unparsed",
        "reason": "ambiguous_multiple_full_earnings_tables",
    }
