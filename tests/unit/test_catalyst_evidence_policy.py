"""Tests for disclosure materiality and catalyst direction separation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.catalyst_evidence_policy import (
    annotate_catalyst_direction,
    apply_catalyst_report_policy,
    gate_catalyst_playbook,
)


def _decode(value: object) -> list[str]:
    assert isinstance(value, str)
    parsed = json.loads(value)
    assert isinstance(parsed, list)
    return [str(item) for item in parsed]


def test_title_only_material_filings_are_not_labeled_positive() -> None:
    catalysts = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "category": "earnings",
                "is_correction": False,
            },
            {
                "ticker": "000660",
                "category": "capex_investment",
                "is_correction": True,
            },
            {
                "ticker": "005930",
                "category": "operational_risk",
                "is_correction": False,
            },
        ]
    )

    result = annotate_catalyst_direction(catalysts)

    assert result.loc[0, "direction_status"] == "unresolved_title_only"
    assert result.loc[1, "direction_status"] == "unresolved_correction_title_only"
    assert result.loc[2, "direction_status"] == "negative_operational_risk_title"
    assert set(result["direction_basis"]) == {"filing_title_only"}
    assert not result["direction_status"].astype(str).str.startswith("positive_").any()


def test_playbook_requires_body_level_direction_verification() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "catalyst_evidence_status": "unresolved_title_only",
                "entry_conditions": json.dumps(["실적 성장 유지"], ensure_ascii=False),
                "add_conditions": json.dumps(["마진 개선 확인"], ensure_ascii=False),
                "reduce_conditions": json.dumps([], ensure_ascii=False),
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
            {
                "ticker": "005930",
                "catalyst_evidence_status": "negative_title_evidence",
                "entry_conditions": json.dumps([], ensure_ascii=False),
                "add_conditions": json.dumps([], ensure_ascii=False),
                "reduce_conditions": json.dumps([], ensure_ascii=False),
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
        ]
    )

    result = gate_catalyst_playbook(scorecards).set_index("ticker")

    hynix_entry = _decode(result.loc["000660", "entry_conditions"])
    hynix_add = _decode(result.loc["000660", "add_conditions"])
    hynix_gaps = _decode(result.loc["000660", "evidence_gaps"])
    samsung_reduce = _decode(result.loc["005930", "reduce_conditions"])
    assert any("본문" in item and "투자 방향" in item for item in hynix_entry)
    assert any("매출·이익·현금흐름" in item for item in hynix_add)
    assert any("시장 기대" in item for item in hynix_gaps)
    assert any("운영위험" in item and "비중 확대 금지" in item for item in samsung_reduce)


def test_report_renames_verified_catalyst_language() -> None:
    report = "\n".join(
        [
            "# Report",
            "",
            "## 실행 플레이북",
            "",
            "- 확인된 촉매",
            "  - 2026-07-29 [earnings] 잠정실적",
        ]
    )

    result = apply_catalyst_report_policy(report)

    assert "확인된 주요 공시·촉매 후보" in result
    assert "본문 검증 전 긍정 촉매로 점수화하지 않음" in result
    assert "- 확인된 촉매\n" not in result


def test_resilient_builder_applies_catalyst_policy() -> None:
    source = Path("src/alpha_cycle/intelligence/decision_resilient.py").read_text(
        encoding="utf-8"
    )

    assert "apply_catalyst_evidence_policy(" in source
    assert "gate_catalyst_playbook(" in source
    assert source.count("report = apply_catalyst_report_policy(") == 2
