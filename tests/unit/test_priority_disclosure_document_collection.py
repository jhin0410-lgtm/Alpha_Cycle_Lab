from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence import fundamental_macro_priority_documents as priority


def _selection_row(
    receipt: str,
    *,
    receipt_date: date,
    category: str,
    material_score: int,
    is_correction: bool,
) -> dict[str, object]:
    return {
        "ticker": "000660",
        "rcept_no": receipt,
        "report_name": (
            f"[기재정정]{category}-{receipt}"
            if is_correction
            else f"{category}-{receipt}"
        ),
        "receipt_date": receipt_date,
        "category": category,
        "priority": "high",
        "material_score": material_score,
        "is_correction": is_correction,
    }


def test_default_capacity_reserves_recent_corrections_without_starving_core() -> None:
    rows: list[dict[str, object]] = []
    for index in range(12):
        rows.append(
            _selection_row(
                f"202606{index + 1:02d}000001",
                receipt_date=date(2026, 6, index + 1),
                category="capex_investment",
                material_score=5,
                is_correction=False,
            )
        )
    for index in range(6):
        rows.append(
            _selection_row(
                f"202607{index + 1:02d}000001",
                receipt_date=date(2026, 7, index + 1),
                category="financing",
                material_score=4,
                is_correction=True,
            )
        )
    frame = pd.DataFrame(rows)

    selected = priority._priority_select_receipts(frame, capacity=12)

    chosen = frame.loc[frame["rcept_no"].isin(selected)]
    assert len(chosen) == 12
    assert int(chosen["is_correction"].sum()) >= 4
    assert int((chosen["category"] == "capex_investment").sum()) >= 6
    assert sum(
        reason == "bounded_recent_correction_reserve"
        for reason in selected.values()
    ) == 4


def test_small_capacity_preserves_materiality_first_behavior() -> None:
    frame = pd.DataFrame(
        [
            _selection_row(
                "20260807000001",
                receipt_date=date(2026, 8, 7),
                category="capex_investment",
                material_score=5,
                is_correction=False,
            ),
            _selection_row(
                "20260807000002",
                receipt_date=date(2026, 8, 7),
                category="financing",
                material_score=4,
                is_correction=True,
            ),
        ]
    )

    selected = priority._priority_select_receipts(frame, capacity=1)

    assert selected == {
        "20260807000001": "bounded_material_event_selection",
    }


def _normalized_event(
    receipt: str,
    *,
    receipt_date: date,
    chain_order: int,
) -> dict[str, object]:
    return {
        "ticker": "005930",
        "rcept_no": receipt,
        "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
        "receipt_date": receipt_date,
        "category": "earnings",
        "priority": "high",
        "material_score": 5,
        "is_correction": chain_order > 0,
        "correction_family_key": "earnings-family",
        "correction_parent_rcept_no": "",
        "correction_chain_root_rcept_no": "20260407800002",
        "correction_chain_order": chain_order,
        "correction_lineage_status": (
            "linked_correction" if chain_order > 0 else "root"
        ),
        "is_latest_in_correction_chain": chain_order > 0,
    }


def test_body_target_support_uses_explicit_target_date_not_heuristic_parent() -> None:
    current_receipt = "20260430800097"
    exact_parent = "20260407800002"
    heuristic_parent = "20260430800083"
    selected = pd.DataFrame(
        [
            _normalized_event(
                current_receipt,
                receipt_date=date(2026, 4, 30),
                chain_order=1,
            )
        ]
    )
    events = pd.DataFrame(
        [
            _normalized_event(
                exact_parent,
                receipt_date=date(2026, 4, 7),
                chain_order=0,
            ),
            _normalized_event(
                heuristic_parent,
                receipt_date=date(2026, 4, 30),
                chain_order=0,
            ),
            _normalized_event(
                current_receipt,
                receipt_date=date(2026, 4, 30),
                chain_order=1,
            ),
        ]
    )
    documents: dict[str, dict[str, object]] = {
        current_receipt: {
            **_normalized_event(
                current_receipt,
                receipt_date=date(2026, 4, 30),
                chain_order=1,
            ),
            "status": "collected",
            "text": "2. 정정 관련 공시서류 제출일 : 2026년 4월 7일",
        },
        heuristic_parent: {
            **_normalized_event(
                heuristic_parent,
                receipt_date=date(2026, 4, 30),
                chain_order=0,
            ),
            "status": "collected",
        },
    }

    pending, warnings = priority._body_target_support_plan(
        selected,
        events,
        documents,
        max_support_documents_per_ticker=4,
        existing_support_receipts={heuristic_parent},
    )

    assert warnings == ()
    assert list(pending["rcept_no"].astype(str)) == [exact_parent]
    assert documents[exact_parent]["status"] == "selected_body_target_support_pending"
    assert documents[exact_parent]["role"] == "correction_body_target_support"
    assert documents[exact_parent]["supports_body_target_receipts"] == [current_receipt]
    assert documents[heuristic_parent]["status"] == "collected"
