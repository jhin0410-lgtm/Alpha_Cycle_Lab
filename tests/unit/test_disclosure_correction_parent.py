"""Tests for explicit body-target correction parent resolution."""

from __future__ import annotations

from alpha_cycle.intelligence.disclosure_correction_delta import (
    verify_correction_delta,
)
from alpha_cycle.intelligence.disclosure_correction_parent import (
    correction_target_submission_date,
    resolve_correction_parent_from_body,
)

CURRENT = "20260430800097"
HEURISTIC_PARENT = "20260430800083"
TARGET_PARENT = "20260407800002"
FAMILY = "연결재무제표기준영업잠정실적공정공시"

_PARENT_BODY = """
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

_WRONG_SAME_DAY_BODY = _PARENT_BODY.replace("133.00", "140.00", 2).replace(
    "57.20", "60.00", 2
)

_CURRENT_BODY = """
정정신고(보고)
정정일자 2026-04-30
1. 정정관련 공시서류 연결재무제표기준영업(잠정)실적(공정공시)
2. 정정관련 공시서류제출일 : 2026년 4월 7일
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


def _record(receipt: str, receipt_date: str, text: str) -> dict[str, object]:
    return {
        "status": "collected",
        "ticker": "005930",
        "rcept_no": receipt,
        "receipt_date": receipt_date,
        "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
        "correction_family_key": FAMILY,
        "correction_parent_rcept_no": "",
        "correction_chain_root_rcept_no": receipt,
        "correction_chain_order": 0,
        "text": text,
        "text_chars": len(text),
        "text_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "text_truncated": False,
    }


def _evidence() -> dict[str, object]:
    current = _record(CURRENT, "2026-04-30", _CURRENT_BODY)
    current.update(
        {
            "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
            "correction_parent_rcept_no": HEURISTIC_PARENT,
            "correction_chain_root_rcept_no": HEURISTIC_PARENT,
            "correction_chain_order": 1,
        }
    )
    heuristic = _record(HEURISTIC_PARENT, "2026-04-30", _WRONG_SAME_DAY_BODY)
    target = _record(TARGET_PARENT, "2026-04-07", _PARENT_BODY)
    return {CURRENT: current, HEURISTIC_PARENT: heuristic, TARGET_PARENT: target}


def test_target_submission_date_parses_korean_body_metadata() -> None:
    target = correction_target_submission_date(_CURRENT_BODY)

    assert target is not None
    assert target.isoformat() == "2026-04-07"


def test_body_target_date_resolves_parent_over_nearest_same_day_filing() -> None:
    evidence = _evidence()
    current = evidence[CURRENT]
    assert isinstance(current, dict)

    resolution = resolve_correction_parent_from_body(current, evidence)

    assert resolution == {
        "status": "resolved",
        "resolution_source": "body_target_submission_date",
        "target_submission_date": "2026-04-07",
        "parent_rcept_no": TARGET_PARENT,
    }


def test_delta_certifies_body_target_parent_despite_wrong_heuristic_parent() -> None:
    evidence = _evidence()
    current = evidence[CURRENT]
    assert isinstance(current, dict)
    catalyst = {
        "ticker": "005930",
        "rcept_no": CURRENT,
        "report_name": current["report_name"],
        "category": "earnings",
        "is_correction": True,
        "correction_parent_rcept_no": HEURISTIC_PARENT,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "verified"
    assert result["parent_rcept_no"] == TARGET_PARENT
    assert result["parent_resolution_source"] == "body_target_submission_date"
    assert result["parent_target_submission_date"] == "2026-04-07"
    assert result["heuristic_parent_rcept_no"] == HEURISTIC_PARENT
    fields = result["fields"]
    assert isinstance(fields, list)
    assert all(row["before_matches_parent"] is True for row in fields)
    assert all(row["after_matches_current"] is True for row in fields)


def test_body_target_parent_ambiguity_fails_closed() -> None:
    evidence = _evidence()
    duplicate = _record("20260407800003", "2026-04-07", _PARENT_BODY)
    evidence["20260407800003"] = duplicate
    current = evidence[CURRENT]
    assert isinstance(current, dict)
    catalyst = {
        "ticker": "005930",
        "rcept_no": CURRENT,
        "report_name": current["report_name"],
        "category": "earnings",
        "is_correction": True,
        "correction_parent_rcept_no": HEURISTIC_PARENT,
    }

    result = verify_correction_delta(catalyst, current, evidence)

    assert result["status"] == "parent_body_target_ambiguous"
    assert result["parent_resolution_source"] == "body_target_submission_date"
    assert result["candidate_rcept_nos"] == [TARGET_PARENT, "20260407800003"]
