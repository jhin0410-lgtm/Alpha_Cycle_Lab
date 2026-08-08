"""Regression coverage for SK hynix 2026-07-10 DR correction-table boundaries."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_corporate_action_delta import (
    corporate_action_delta_rows,
)


LIVE_SHAPED_DR_CORRECTION = """
정정신고(보고)
정정일자 2026-07-10
1. 정정관련 공시서류 증권예탁증권(DR) 발행 결정
2. 정정관련 공시서류제출일 2026-06-24
3. 정정사유 발행 조건 확정에 따른 기재 정정
4. 정정사항
정정항목 정정전 정정후
2. DR 발행총액 - 외화금액(통화단위)
외화금액: - (통화단위): KRW
외화금액: 26,507,100,000 (통화단위): USD
2. DR 발행총액 - 원화금액(원)
43,140,750,000,000 40,023,070,290,000
2. DR 발행총액 - 기준환율등
- 1,509.90
3. 신주DR의 경우 신주발행가액(원) - 보통주식
2,425,000 2,249,751
4. 1 DR당 발행가액(통화단위)
발행가액: 242,500 (통화단위): KRW
발행가액: 149.00 (통화단위): USD
7. 자금조달의 목적 - 시설자금(원)
43,140,750,000,000 40,023,070,290,000
18. 기타 투자판단과 관련한 중요사항
정정 전: 17,790,000주에 2026년 7월 3일 종가 2,425,000원을 적용
정정 후: 확정 발행가액 2,249,751원과 환율 1,509.90원을 적용

증권예탁증권(DR) 발행 결정
1. DR 발행형태 신주DR
"""


def test_dr_delta_ignores_adjacent_fx_and_narrative_numbers() -> None:
    rows = corporate_action_delta_rows(
        "depositary_receipt_issuance",
        LIVE_SHAPED_DR_CORRECTION,
    )

    by_field = {str(row["field"]): row for row in rows}
    assert by_field["dr_total_krw"] == {
        "field": "dr_total_krw",
        "before": 43_140_750_000_000,
        "after": 40_023_070_290_000,
        "changed": True,
    }
    assert by_field["share_issue_price_krw"] == {
        "field": "share_issue_price_krw",
        "before": 2_425_000,
        "after": 2_249_751,
        "changed": True,
    }
    assert by_field["facility_funding_krw"] == {
        "field": "facility_funding_krw",
        "before": 43_140_750_000_000,
        "after": 40_023_070_290_000,
        "changed": True,
    }
