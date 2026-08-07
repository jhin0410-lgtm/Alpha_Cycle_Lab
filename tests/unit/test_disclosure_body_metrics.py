"""Tests for deterministic metrics parsed from pinned disclosure bodies."""

from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.catalyst_evidence_policy import (
    annotate_catalyst_direction,
    _direction_counts,
)
from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics,
)


EARNINGS_CORRECTION_BODY = """
정정신고(보고)
정정일자 2026-04-30
1. 정정관련 공시서류 연결재무제표기준영업(잠정)실적(공정공시)
4. 정정사항
정정항목 정정전 정정후
매출액(당해실적) 133.00 133.87
영업이익(당해실적) 57.20 57.23

연결재무제표 기준 영업(잠정)실적(공정공시)
실적기간
당기실적 2026-01-01 ~ 2026-03-31
1. 연결실적내용
단위 : 조원, %
구분 당기실적 전기실적 전기대비 전년동기실적 전년동기대비
매출액 당해실적 133.87 93.84 42.67 - 79.14 69.16 -
누계실적 133.87 - - - 79.14 69.16 -
영업이익 당해실적 57.23 20.07 185.11 - 6.69 756.10 -
누계실적 57.23 - - - 6.69 756.10 -
당기순이익 당해실적 - - - - - - -
누계실적 - - - - - - -
2. 정보제공내역 정보제공자 IR팀
"""

CAPEX_CORRECTION_BODY = """
정정신고(보고)
정정일자 2026-06-15
1. 정정관련 공시서류 신규시설투자등
4. 정정사항
정정항목 정정전 정정후
투자금액(원) 17,667,400,000 18,095,700,000
자기자본대비(%) 24.1 24.7

신규 시설투자 등
1. 투자구분 신규시설투자등(공장신증축 및 설비투자)
2. 투자내역 투자금액(원) 18,095,700,000
자기자본(원) 73,201,826,510
자기자본대비(%) 24.7
대규모법인여부 미해당
3. 투자목적 반도체 소재 공장 신증축 및 설비투자
4. 투자기간 시작일 2025-09-24 종료일 2026-12-31
5. 이사회결의일(결정일) 2026-01-23
"""


def test_earnings_parser_uses_final_corrected_table_not_correction_header() -> None:
    result = parse_disclosure_body_metrics(
        "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        EARNINGS_CORRECTION_BODY,
    )

    assert result["status"] == "verified"
    assert result["type"] == "earnings_preliminary"
    assert result["unit"] == "조원"
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    sales = metrics["sales"]
    operating_profit = metrics["operating_profit"]
    assert sales["current"] == "133.87"
    assert sales["previous_quarter"] == "93.84"
    assert sales["qoq_pct"] == "42.67"
    assert sales["prior_year"] == "79.14"
    assert sales["yoy_pct"] == "69.16"
    assert sales["current_krw"] == 133_870_000_000_000
    assert operating_profit["current"] == "57.23"
    assert operating_profit["current_krw"] == 57_230_000_000_000


def test_capex_parser_uses_final_corrected_table_and_fixed_krw_fields() -> None:
    result = parse_disclosure_body_metrics(
        "[기재정정]신규시설투자등",
        CAPEX_CORRECTION_BODY,
    )

    assert result == {
        "schema_version": 1,
        "type": "facility_investment",
        "status": "verified",
        "investment_amount_krw": 18_095_700_000,
        "equity_krw": 73_201_826_510,
        "equity_ratio_pct": "24.7",
        "purpose": "반도체 소재 공장 신증축 및 설비투자",
        "start_date": "2025-09-24",
        "end_date": "2026-12-31",
    }


def test_supported_parser_fails_closed_when_required_fields_are_missing() -> None:
    result = parse_disclosure_body_metrics(
        "신규시설투자등",
        "신규 시설투자 등 2. 투자내역 투자금액(원) 1,000,000",
    )

    assert result["status"] == "partial"
    assert result["investment_amount_krw"] == 1_000_000
    assert result["reason"] == "required_capex_fields_missing"


def test_unsupported_report_type_is_not_inferred() -> None:
    result = parse_disclosure_body_metrics(
        "유형자산취득결정",
        "투자금액(원) 100000000 자기자본대비(%) 5.0",
    )

    assert result == {
        "schema_version": 1,
        "type": "unsupported",
        "status": "unsupported_report_type",
    }


def test_catalyst_policy_binds_metrics_to_pinned_body_hashes_without_scoring() -> None:
    catalysts = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260430800001",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "category": "earnings",
                "is_correction": True,
            }
        ]
    )
    evidence: dict[str, object] = {
        "20260430800001": {
            "status": "collected",
            "role": "primary_catalyst",
            "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
            "text": EARNINGS_CORRECTION_BODY,
            "text_chars": len(EARNINGS_CORRECTION_BODY),
            "text_sha256": "a" * 64,
            "archive_sha256": "b" * 64,
            "text_truncated": False,
        }
    }

    result = annotate_catalyst_direction(
        catalysts,
        document_evidence=evidence,
    )

    assert result.loc[0, "direction_status"] == (
        "unresolved_correction_body_metrics_verified"
    )
    assert result.loc[0, "direction_basis"] == (
        "filing_body_metrics_verified_unscored"
    )
    assert result.loc[0, "body_metrics_status"] == "verified"
    assert result.loc[0, "body_metrics_type"] == "earnings_preliminary"
    payload = json.loads(str(result.loc[0, "body_metrics_json"]))
    assert payload["metrics"]["sales"]["current"] == "133.87"
    counts = _direction_counts(result)["005930"]
    assert counts["unresolved_body"] == 1
    assert counts["verified_metrics"] == 1
    assert counts["unresolved_title"] == 0
