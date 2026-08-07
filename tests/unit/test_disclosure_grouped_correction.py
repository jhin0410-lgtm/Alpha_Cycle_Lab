"""Regression tests for grouped-column correction tables after text flattening."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_correction_delta import (
    verify_correction_delta,
)

CURRENT_RECEIPT = "20260430800001"
PARENT_RECEIPT = "20260407800001"
FAMILY = "연결재무제표기준영업잠정실적공정공시"

PARENT_BODY = """
연결재무제표 기준 영업(잠정)실적(공정공시)
1. 연결실적내용
단위 : 조원, %
구분 당기실적 전기실적 전기대비 전년동기실적 전년동기대비
매출액 당해실적 133.00 93.84 41.73 - 79.14 68.06 -
누계실적 133.00 - - - 79.14 68.06 -
영업이익 당해실적 57.20 20.07 185.00 - 6.69 755.01 -
누계실적 57.20 - - - 6.69 755.01 -
당기순이익 당해실적 - - - - - - -
누계실적 - - - - - - -
"""

GROUPED_CURRENT_BODY = """
정정신고(보고)
정정일자
2026-04-30
1. 정정관련 공시서류
연결재무제표기준영업(잠정)실적(공정공시)
2. 정정관련 공시서류제출일
2026년 4월 7일
3. 정정사유
2026년 1분기 연결재무제표기준영업(잠정)실적(공정공시) 내용 정정
4. 정정사항
정정항목
정정전
정정후
1. 연결실적내용
·당기실적('26.1Q)
- 매출액(당해실적)
- 매출액(누계실적)
- 영업이익(당해실적)
- 영업이익(누계실적)
133.00
133.00
57.20
57.20
133.87
133.87
57.23
57.23
·전기대비증감율(%)
- 매출액(당해실적)
- 영업이익(당해실적)
41.73
185.00
42.67
185.11

연결재무제표 기준 영업(잠정)실적(공정공시)
1. 연결실적내용
단위 : 조원, %
구분 당기실적 전기실적 전기대비 전년동기실적 전년동기대비
매출액 당해실적 133.87 93.84 42.67 - 79.14 69.16 -
누계실적 133.87 - - - 79.14 69.16 -
영업이익 당해실적 57.23 20.07 185.11 - 6.69 756.10 -
누계실적 57.23 - - - 6.69 756.10 -
당기순이익 당해실적 - - - - - - -
누계실적 - - - - - - -
"""


def _record(
    *,
    receipt: str,
    receipt_date: str,
    report_name: str,
    text: str,
    order: int,
    parent: str = "",
    supporters: list[str] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "status": "collected",
        "ticker": "005930",
        "rcept_no": receipt,
        "receipt_date": receipt_date,
        "report_name": report_name,
        "correction_family_key": FAMILY,
        "correction_parent_rcept_no": parent,
        "correction_chain_root_rcept_no": PARENT_RECEIPT,
        "correction_chain_order": order,
        "text": text,
        "text_chars": len(text),
        "text_sha256": ("a" if order else "c") * 64,
        "archive_sha256": ("b" if order else "d") * 64,
        "text_truncated": False,
    }
    if supporters is not None:
        record["supports_selected_receipts"] = supporters
    return record


def test_grouped_samsung_style_correction_table_certifies_against_parent() -> None:
    current = _record(
        receipt=CURRENT_RECEIPT,
        receipt_date="2026-04-30",
        report_name="[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        text=GROUPED_CURRENT_BODY,
        order=1,
        parent=PARENT_RECEIPT,
    )
    parent = _record(
        receipt=PARENT_RECEIPT,
        receipt_date="2026-04-07",
        report_name="연결재무제표기준영업(잠정)실적(공정공시)",
        text=PARENT_BODY,
        order=0,
        supporters=[CURRENT_RECEIPT],
    )
    evidence: dict[str, object] = {
        CURRENT_RECEIPT: current,
        PARENT_RECEIPT: parent,
    }
    catalyst = {
        "ticker": "005930",
        "rcept_no": CURRENT_RECEIPT,
        "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        "category": "earnings",
        "is_correction": True,
        "correction_parent_rcept_no": PARENT_RECEIPT,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "verified"
    assert result["parent_resolution_source"] == "body_target_submission_date"
    assert result["parent_target_submission_date"] == "2026-04-07"
    assert result["changed_field_count"] == 2
    fields = result["fields"]
    assert isinstance(fields, list)
    sales = next(row for row in fields if row["field"] == "sales")
    operating = next(row for row in fields if row["field"] == "operating_profit")
    assert sales["before"] == "133.00"
    assert sales["after"] == "133.87"
    assert operating["before"] == "57.20"
    assert operating["after"] == "57.23"
    assert all(row["before_matches_parent"] is True for row in fields)
    assert all(row["after_matches_current"] is True for row in fields)


def test_grouped_parser_fails_closed_when_numeric_columns_are_incomplete() -> None:
    current = _record(
        receipt=CURRENT_RECEIPT,
        receipt_date="2026-04-30",
        report_name="[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        text=GROUPED_CURRENT_BODY.replace("57.23\n57.23", "57.23", 1),
        order=1,
        parent=PARENT_RECEIPT,
    )
    parent = _record(
        receipt=PARENT_RECEIPT,
        receipt_date="2026-04-07",
        report_name="연결재무제표기준영업(잠정)실적(공정공시)",
        text=PARENT_BODY,
        order=0,
        supporters=[CURRENT_RECEIPT],
    )
    evidence: dict[str, object] = {
        CURRENT_RECEIPT: current,
        PARENT_RECEIPT: parent,
    }
    catalyst = {
        "ticker": "005930",
        "rcept_no": CURRENT_RECEIPT,
        "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        "category": "earnings",
        "is_correction": True,
        "correction_parent_rcept_no": PARENT_RECEIPT,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] != "verified"
