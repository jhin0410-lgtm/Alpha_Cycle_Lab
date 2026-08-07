"""Tests for fail-closed supported correction delta certification."""

from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.catalyst_evidence_policy import (
    _direction_counts,
    annotate_catalyst_direction,
)
from alpha_cycle.intelligence.disclosure_body_metrics import (
    parse_disclosure_body_metrics,
)
from alpha_cycle.intelligence.disclosure_correction_delta import (
    verify_correction_delta,
)

CURRENT_RECEIPT = "20260430800001"
PARENT_RECEIPT = "20260407800001"
FAMILY = "연결재무제표기준영업잠정실적공정공시"

PARENT_EARNINGS_BODY = """
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

CURRENT_EARNINGS_BODY = """
정정신고(보고)
정정일자 2026-04-30
1. 정정관련 공시서류 연결재무제표기준영업(잠정)실적(공정공시)
4. 정정사항
정정항목 정정전 정정후
매출액(당해실적) 133.00 133.87
영업이익(당해실적) 57.20 57.23

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

PARENT_CAPEX_BODY = """
신규 시설투자 등
1. 투자구분 신규시설투자등(공장신증축 및 설비투자)
2. 투자내역 투자금액(원) 17,667,400,000
자기자본(원) 73,201,826,510
자기자본대비(%) 24.1
대규모법인여부 미해당
3. 투자목적 반도체 소재 공장 신증축 및 설비투자
4. 투자기간 시작일 2025-09-24 종료일 2026-12-31
"""

CURRENT_CAPEX_BODY = """
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
"""


def _record(
    *,
    receipt: str,
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


def _earnings_evidence() -> dict[str, object]:
    return {
        CURRENT_RECEIPT: _record(
            receipt=CURRENT_RECEIPT,
            report_name=(
                "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)"
            ),
            text=CURRENT_EARNINGS_BODY,
            order=1,
            parent=PARENT_RECEIPT,
        ),
        PARENT_RECEIPT: _record(
            receipt=PARENT_RECEIPT,
            report_name="연결재무제표기준영업(잠정)실적(공정공시)",
            text=PARENT_EARNINGS_BODY,
            order=0,
            supporters=[CURRENT_RECEIPT],
        ),
    }


def _catalyst() -> dict[str, object]:
    return {
        "ticker": "005930",
        "rcept_no": CURRENT_RECEIPT,
        "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
        "category": "earnings",
        "is_correction": True,
        "correction_parent_rcept_no": PARENT_RECEIPT,
        "correction_family_key": FAMILY,
        "correction_chain_root_rcept_no": PARENT_RECEIPT,
        "correction_chain_order": 1,
    }


def test_earnings_delta_requires_before_parent_and_after_current_match() -> None:
    evidence = _earnings_evidence()
    current = evidence[CURRENT_RECEIPT]
    assert isinstance(current, dict)
    metrics = parse_disclosure_body_metrics(
        current["report_name"],
        current["text"],
    )

    result = verify_correction_delta(
        _catalyst(),
        current,
        evidence,
        current_metrics=metrics,
    )

    assert result["status"] == "verified"
    assert result["scope"] == "supported_fields_only"
    assert result["metric_type"] == "earnings_preliminary"
    assert result["changed_field_count"] == 2
    fields = result["fields"]
    assert isinstance(fields, list)
    assert {row["field"] for row in fields} == {"sales", "operating_profit"}
    assert all(row["before_matches_parent"] is True for row in fields)
    assert all(row["after_matches_current"] is True for row in fields)


def test_delta_fails_closed_when_parent_value_does_not_match_header_before() -> None:
    evidence = _earnings_evidence()
    parent = evidence[PARENT_RECEIPT]
    assert isinstance(parent, dict)
    parent["text"] = PARENT_EARNINGS_BODY.replace("133.00", "132.00", 2)
    parent["text_chars"] = len(str(parent["text"]))
    current = evidence[CURRENT_RECEIPT]
    assert isinstance(current, dict)

    result = verify_correction_delta(_catalyst(), current, evidence)

    assert result["status"] == "value_mismatch"
    fields = result["fields"]
    assert isinstance(fields, list)
    sales = next(row for row in fields if row["field"] == "sales")
    assert sales["before_matches_parent"] is False
    assert sales["after_matches_current"] is True


def test_delta_fails_closed_when_support_binding_is_missing() -> None:
    evidence = _earnings_evidence()
    parent = evidence[PARENT_RECEIPT]
    current = evidence[CURRENT_RECEIPT]
    assert isinstance(parent, dict)
    assert isinstance(current, dict)
    parent["supports_selected_receipts"] = []

    result = verify_correction_delta(_catalyst(), current, evidence)

    assert result["status"] == "parent_lineage_binding_mismatch"


def test_capex_delta_verifies_fixed_krw_and_ratio_fields() -> None:
    current_receipt = "20260615800002"
    parent_receipt = "20260123800002"
    family = "신규시설투자등"
    current = _record(
        receipt=current_receipt,
        report_name="[기재정정]신규시설투자등",
        text=CURRENT_CAPEX_BODY,
        order=1,
        parent=parent_receipt,
    )
    parent = _record(
        receipt=parent_receipt,
        report_name="신규시설투자등",
        text=PARENT_CAPEX_BODY,
        order=0,
        supporters=[current_receipt],
    )
    for record in (current, parent):
        record["correction_family_key"] = family
        record["correction_chain_root_rcept_no"] = parent_receipt
    catalyst = {
        "ticker": "005930",
        "rcept_no": current_receipt,
        "report_name": "[기재정정]신규시설투자등",
        "category": "capex_investment",
        "is_correction": True,
        "correction_parent_rcept_no": parent_receipt,
    }
    evidence: dict[str, object] = {
        current_receipt: current,
        parent_receipt: parent,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "verified"
    assert result["metric_type"] == "facility_investment"
    assert result["changed_field_count"] == 2


def test_catalyst_annotation_surfaces_verified_delta_without_scoring_direction() -> None:
    catalysts = pd.DataFrame([_catalyst()])
    evidence = _earnings_evidence()

    result = annotate_catalyst_direction(catalysts, document_evidence=evidence)

    assert result.loc[0, "direction_status"] == "unresolved_correction_delta_verified"
    assert result.loc[0, "direction_basis"] == (
        "filing_correction_delta_verified_unscored"
    )
    assert result.loc[0, "correction_delta_status"] == "verified"
    payload = json.loads(str(result.loc[0, "correction_delta_json"]))
    assert payload["changed_field_count"] == 2
    assert result.loc[0, "correction_parent_rcept_no"] == PARENT_RECEIPT
    assert result.loc[0, "correction_parent_text_sha256"] == "c" * 64
    counts = _direction_counts(result)["005930"]
    assert counts["unresolved_body"] == 1
    assert counts["verified_metrics"] == 1
    assert counts["verified_correction_deltas"] == 1
