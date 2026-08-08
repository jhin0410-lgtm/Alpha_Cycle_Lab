"""Corporate-action body metrics and correction-delta certification tests."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics,
)
from alpha_cycle.intelligence.disclosure_correction_delta import (
    verify_correction_delta,
)

ROOT_RECEIPT = "20260624000001"
PARENT_RECEIPT = "20260706000001"
CURRENT_RECEIPT = "20260710000001"

PARENT_EQUITY_BODY = """
유상증자 결정
1. 신주의 종류와 수 보통주식 (주) 17,790,000 기타주식 (주) -
2. 1주당 액면가액 (원) 5,000
3. 증자전 발행주식총수 (주) 보통주식 (주) 712,702,365 기타주식 (주) -
4. 자금조달의 목적 시설자금 (원) 43,140,750,000,000 운영자금 (원) -
5. 증자방식 제3자배정증자
6. 신주 발행가액 보통주식 (원) 2,425,000 기타주식 (원) -
7. 기준주가 보통주식 (원) - 기타주식 (원) -
7-1. 기준주가 산정방법 -
7-2. 기준주가에 대한 할인율 또는 할증율 (%) -
7-3. 할인율(할증률) 산정 근거 -
9. 납입일 2026.07.14
12. 신주의 상장 예정일 2026.07.29
"""

CURRENT_EQUITY_BODY = """
정 정 신 고 (보고)
1. 정정 관련 공시서류 제출일 2026년 06월 24일
3. 정정사항
항 목 정정사유 정 정 전 정 정 후
4. 자금조달의 목적 - 시설자금(원)
발행 조건 확정 43,140,750,000,000 40,023,070,290,000
6. 신주 발행가액 - 보통주식(원) 2,425,000 2,249,751
7. 기준주가 - 보통주식(원) - 2,190,229
7-2. 기준주가에 대한 할인율 또는 할증율(%) - 2.72
20. 기타 투자판단에 참고할 사항 정정 전 정정 후

유상증자 결정
1. 신주의 종류와 수 보통주식 (주) 17,790,000 기타주식 (주) -
2. 1주당 액면가액 (원) 5,000
3. 증자전 발행주식총수 (주) 보통주식 (주) 712,702,365 기타주식 (주) -
4. 자금조달의 목적 시설자금 (원) 40,023,070,290,000 운영자금 (원) -
5. 증자방식 제3자배정증자
6. 신주 발행가액 보통주식 (원) 2,249,751 기타주식 (원) -
7. 기준주가 보통주식 (원) 2,190,229 기타주식 (원) -
7-1. 기준주가 산정방법 가중산술평균주가
7-2. 기준주가에 대한 할인율 또는 할증율 (%) 2.72
7-3. 할인율(할증률) 산정 근거 -
9. 납입일 2026.07.14
12. 신주의 상장 예정일 2026.07.29
"""

PARENT_DR_BODY = """
증권예탁증권(DR) 발행 결정
1. DR 발행형태 신주DR
2. DR 발행총액 외화금액 (통화단위) - KRW : South-Korean Won
원화금액(원) 43,140,750,000,000 기준환율등 -
3. 신주DR의 경우 신주 발행가액(원) 보통주식 2,425,000 종류주식 -
4. 1 DR당 발행가액(통화단위) 242,500 KRW/1DR : South-Korean Won
- 원주의종류 보통주식
5. 1 DR당 원주 전환비율(주) 0.1
6. 발행국가 해외시장(미국)
7. 자금조달의 목적 시설자금(원) 43,140,750,000,000 운영자금(원) -
8. 청약일 2026-07-14
9. 납입일 2026-07-14
10. 해외 상장의 경우 상장거래소 나스닥 증권거래소 상장예정일 2026-07-10
11. 신주DR의 경우 신주상장예정일 2026-07-29
"""

CURRENT_DR_BODY = """
정 정 신 고 (보고)
1. 정정 관련 공시서류 제출일 2026년 06월 24일
3. 정정사항
항 목 정정사유 정 정 전 정 정 후
2. DR 발행총액 원화금액(원) 43,140,750,000,000 40,023,070,290,000
3. 신주DR의 경우 신주 발행가액(원) 보통주식 2,425,000 2,249,751
7. 자금조달의 목적 시설자금(원) 43,140,750,000,000 40,023,070,290,000

증권예탁증권(DR) 발행 결정
1. DR 발행형태 신주DR
2. DR 발행총액 외화금액 (통화단위) 26,507,100,000 USD : US Dollar
원화금액(원) 40,023,070,290,000 기준환율등 1,509.90
3. 신주DR의 경우 신주 발행가액(원) 보통주식 2,249,751 종류주식 -
4. 1 DR당 발행가액(통화단위) 149.00 USD/1DR : US Dollar - 원주의종류 보통주식
5. 1 DR당 원주 전환비율(주) 0.1
6. 발행국가 해외시장(미국)
7. 자금조달의 목적 시설자금(원) 40,023,070,290,000 운영자금(원) -
8. 청약일 2026-07-14
9. 납입일 2026-07-14
10. 해외 상장의 경우 상장거래소 나스닥 증권거래소 상장예정일 2026-07-10
11. 신주DR의 경우 신주상장예정일 2026-07-29
"""

OVERSEAS_LISTING_BODY = """
해외 증권시장 주권등 상장 결정
1. 상장예정주식 종류ㆍ수(주) 보통주식 17,790,000 기타주식 -
- 발행주식 총수(주) 보통주식 712,702,365 기타주식 -
2. 공모방법 신주발행 (주) 17,790,000 구주매출 (주) -
3. 자금조달(신주발행) 목적 시설자금
4. 상장증권 원주상장 (주) - DR상장 (주) 177,900,000
5. 상장거래소(소재국가) 미국 나스닥 증권거래소 (Nasdaq Global Select Market)
6. 해외상장목적 글로벌 투자자 기반 확장
7. 상장예정일자 2026.07.10
"""


def _record(
    receipt: str,
    report_name: str,
    text: str,
    order: int,
    *,
    parent: str = "",
    supporters: list[str] | None = None,
    family: str,
) -> dict[str, object]:
    record: dict[str, object] = {
        "status": "collected",
        "ticker": "000660",
        "rcept_no": receipt,
        "report_name": report_name,
        "correction_family_key": family,
        "correction_parent_rcept_no": parent,
        "correction_chain_root_rcept_no": ROOT_RECEIPT,
        "correction_chain_order": order,
        "text": text,
        "text_chars": len(text),
        "text_sha256": ("a" if order == 2 else "c") * 64,
        "archive_sha256": ("b" if order == 2 else "d") * 64,
        "text_truncated": False,
    }
    if supporters is not None:
        record["supports_selected_receipts"] = supporters
    return record


def test_equity_issuance_final_form_metrics_are_verified() -> None:
    result = parse_disclosure_body_metrics(
        "[기재정정]주요사항보고서(유상증자결정)",
        CURRENT_EQUITY_BODY,
    )

    assert result["status"] == "verified"
    assert result["type"] == "equity_issuance"
    assert result["common_shares_issued"] == 17_790_000
    assert result["pre_issue_common_shares"] == 712_702_365
    assert result["facility_funding_krw"] == 40_023_070_290_000
    assert result["issue_price_krw"] == 2_249_751
    assert result["reference_price_krw"] == 2_190_229
    assert result["premium_discount_pct"] == "2.72"


def test_dr_final_form_metrics_keep_price_currency_explicit() -> None:
    result = parse_disclosure_body_metrics(
        "[기재정정]증권예탁증권(DR)발행결정",
        CURRENT_DR_BODY,
    )

    assert result["status"] == "verified"
    assert result["type"] == "depositary_receipt_issuance"
    assert result["dr_total_krw"] == 40_023_070_290_000
    assert result["share_issue_price_krw"] == 2_249_751
    assert result["dr_price"] == "149.00"
    assert result["dr_price_currency"] == "USD"
    assert result["original_share_per_dr"] == "0.1"
    assert result["facility_funding_krw"] == 40_023_070_290_000


def test_overseas_listing_body_is_structured_without_direction() -> None:
    result = parse_disclosure_body_metrics(
        "[기재정정]주요사항보고서(해외증권시장주권등상장결정)",
        OVERSEAS_LISTING_BODY,
    )

    assert result["status"] == "verified"
    assert result["type"] == "overseas_listing"
    assert result["common_shares_to_list"] == 17_790_000
    assert result["pre_issue_common_shares"] == 712_702_365
    assert result["new_shares"] == 17_790_000
    assert result["dr_shares"] == 177_900_000
    assert result["listing_date"] == "2026-07-10"


def test_second_equity_correction_uses_immediate_chain_parent() -> None:
    family = "유상증자결정"
    current = _record(
        CURRENT_RECEIPT,
        "[기재정정]주요사항보고서(유상증자결정)",
        CURRENT_EQUITY_BODY,
        2,
        parent=PARENT_RECEIPT,
        family=family,
    )
    parent = _record(
        PARENT_RECEIPT,
        "[기재정정]주요사항보고서(유상증자결정)",
        PARENT_EQUITY_BODY,
        1,
        parent=ROOT_RECEIPT,
        supporters=[CURRENT_RECEIPT],
        family=family,
    )
    evidence: dict[str, object] = {
        CURRENT_RECEIPT: current,
        PARENT_RECEIPT: parent,
    }
    catalyst = {
        "ticker": "000660",
        "rcept_no": CURRENT_RECEIPT,
        "report_name": "[기재정정]주요사항보고서(유상증자결정)",
        "is_correction": True,
        "correction_parent_rcept_no": PARENT_RECEIPT,
        "correction_chain_order": 2,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "verified"
    assert result["metric_type"] == "equity_issuance"
    assert result["parent_rcept_no"] == PARENT_RECEIPT
    assert result["parent_resolution_source"] == "correction_chain_parent"
    assert result["changed_field_count"] == 4
    assert result["verified_field_count"] == 4


def test_second_dr_correction_verifies_same_unit_numeric_fields_only() -> None:
    family = "증권예탁증권dr발행결정"
    current = _record(
        CURRENT_RECEIPT,
        "[기재정정]증권예탁증권(DR)발행결정",
        CURRENT_DR_BODY,
        2,
        parent=PARENT_RECEIPT,
        family=family,
    )
    parent = _record(
        PARENT_RECEIPT,
        "[기재정정]증권예탁증권(DR)발행결정",
        PARENT_DR_BODY,
        1,
        parent=ROOT_RECEIPT,
        supporters=[CURRENT_RECEIPT],
        family=family,
    )
    evidence: dict[str, object] = {
        CURRENT_RECEIPT: current,
        PARENT_RECEIPT: parent,
    }
    catalyst = {
        "ticker": "000660",
        "rcept_no": CURRENT_RECEIPT,
        "report_name": "[기재정정]증권예탁증권(DR)발행결정",
        "is_correction": True,
        "correction_parent_rcept_no": PARENT_RECEIPT,
        "correction_chain_order": 2,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "verified"
    assert result["metric_type"] == "depositary_receipt_issuance"
    assert result["parent_resolution_source"] == "correction_chain_parent"
    fields = result["fields"]
    assert isinstance(fields, list)
    assert {row["field"] for row in fields} == {
        "dr_total_krw",
        "share_issue_price_krw",
        "facility_funding_krw",
    }
    assert all(row["before_matches_parent"] is True for row in fields)
    assert all(row["after_matches_current"] is True for row in fields)
