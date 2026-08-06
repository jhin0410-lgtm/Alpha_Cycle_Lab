"""Regression coverage for price-adjustment technical evidence policy."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.technical_evidence_policy import (
    apply_market_report_policy,
    gate_execution_playbook,
    gate_market_context,
)


def _decode(value: object) -> list[str]:
    assert isinstance(value, str)
    parsed = json.loads(value)
    assert isinstance(parsed, list)
    return [str(item) for item in parsed]


def _market_context() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "last_price": 200_000.0,
                "return_20": -0.28,
                "return_60": -0.205,
                "sma_20": 235_000.0,
                "price_to_sma_20": -0.152,
                "max_drawdown_60": -0.547,
                "relative_strength_rank_20": 0.5,
                "trend_direction_20": -1.0,
            }
        ]
    )


def test_unadjusted_market_context_preserves_observations_but_gates_signals() -> None:
    result = gate_market_context(_market_context(), adjusted=False).iloc[0]

    assert result["price_adjustment_basis"] == "unadjusted"
    assert bool(result["technical_decision_eligible"]) is False
    assert pd.isna(result["return_20"])
    assert pd.isna(result["price_to_sma_20"])
    assert result["observed_return_20"] == pytest.approx(-0.28)
    assert result["observed_price_to_sma_20"] == pytest.approx(-0.152)
    assert result["last_price"] == pytest.approx(200_000.0)


def test_adjusted_market_context_remains_execution_eligible() -> None:
    result = gate_market_context(_market_context(), adjusted=True).iloc[0]

    assert result["price_adjustment_basis"] == "adjusted"
    assert bool(result["technical_decision_eligible"]) is True
    assert result["return_20"] == pytest.approx(-0.28)
    assert "observed_return_20" not in result.index


def test_unknown_adjustment_basis_is_fail_closed() -> None:
    result = gate_market_context(_market_context(), adjusted=None).iloc[0]

    assert result["price_adjustment_basis"] == "unknown"
    assert bool(result["technical_decision_eligible"]) is False
    assert pd.isna(result["return_20"])
    assert result["observed_return_20"] == pytest.approx(-0.28)


def test_playbook_removes_unadjusted_price_execution_thresholds() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "decision_state": "positive_setup",
                "action_readiness": "wait_for_timing_confirmation",
                "entry_conditions": json.dumps(
                    [
                        "20일선 회복과 20일 수익률 양전 등 가격 확인 후 검토",
                        "최근 실적 또는 핵심 공시에 부정적 정정이 없을 것",
                        "20일 상대강도와 20일선 방향이 동시에 악화되지 않을 것",
                    ],
                    ensure_ascii=False,
                ),
                "add_conditions": json.dumps(
                    [
                        "다음 실적에서 영업이익 YoY와 영업이익률이 기존 투자 논리를 확인",
                        "주가 상승이 거래량 또는 상대강도 개선과 동반",
                    ],
                    ensure_ascii=False,
                ),
                "reduce_conditions": json.dumps(
                    [
                        "20일 수익률이 -10% 이하이면서 20일선을 하회",
                        "현재 약세가 상대강도 하위권 고착으로 이어짐",
                        "영업이익률이 전년 대비 3%p 이상 악화",
                    ],
                    ensure_ascii=False,
                ),
                "exit_conditions": json.dumps(
                    [
                        "20일 수익률 -10% 이하이면서 20일선 하회",
                        "이익 모멘텀과 가격 추세가 동시에 훼손되어 원래 기대수익 경로가 사라짐",
                        "영업이익 YoY가 0% 이하로 전환",
                    ],
                    ensure_ascii=False,
                ),
                "evidence_gaps": json.dumps([], ensure_ascii=False),
                "playbook_basis": "deterministic_snapshot_rules_no_future_event_dates",
            }
        ]
    )
    market = gate_market_context(_market_context(), adjusted=False)

    result = gate_execution_playbook(scorecards, market).iloc[0]

    assert result["action_readiness"] == "wait_for_adjusted_market_evidence"
    entry = _decode(result["entry_conditions"])
    additions = _decode(result["add_conditions"])
    reductions = _decode(result["reduce_conditions"])
    exits = _decode(result["exit_conditions"])
    gaps = _decode(result["evidence_gaps"])
    assert any("수정주가" in item for item in entry)
    assert all("20일" not in item and "상대강도" not in item for item in entry)
    assert any("기업행위 검증" in item for item in additions)
    assert all("상대강도" not in item for item in additions)
    assert any("기술 신호만으로 비중을 축소하지 않음" in item for item in reductions)
    assert all("20일" not in item and "상대강도" not in item for item in reductions)
    assert all("20일 수익률" not in item for item in exits)
    assert any("수정주가 기준 가격 추세" in item for item in exits)
    assert any("가격 이력 미확보" in item for item in gaps)
    assert str(result["playbook_basis"]).endswith("_technical_execution_gated")


def test_report_labels_unadjusted_observations_as_non_executable() -> None:
    market = gate_market_context(_market_context(), adjusted=False)
    report = "\n".join(
        [
            "# Alpha Cycle 투자 의사결정 리포트",
            "",
            "## 000660",
            "",
            "### 3. 시장 타이밍",
            "",
            "- 20일 수익률: N/A",
            "",
            "### 6. 시나리오",
            "",
            "- Bull: 이익 성장·마진 개선·핵심 촉매·상대강도가 함께 유지",
            "- Base: 현재 실적 성장률과 마진·환율·가격 추세가 대체로 유지",
            "- Bear: 이익 둔화·마진 압박·촉매 지연·20일선 하회가 동시 발생",
        ]
    )

    result = apply_market_report_policy(report, market)

    assert "가격 조정 기준: unadjusted" in result
    assert "실행용 기술 지표는 미평가" in result
    assert "가격 조정 미검증 시장 관측치" in result
    assert "관측 20일 수익률: -28.0%" in result
    assert "종합점수, 행동 준비도" in result
    assert "가격 타이밍은 미평가" in result
    assert "촉매 지연이 동시 발생" in result
    assert "20일선 하회가 동시 발생" not in result


def test_resilient_builder_applies_market_policy_before_playbook() -> None:
    source = Path("src/alpha_cycle/intelligence/decision_resilient.py").read_text(
        encoding="utf-8"
    )

    assert "apply_market_evidence_policy(" in source
    assert "gate_execution_playbook(" in source
    assert source.count("report = apply_market_report_policy(") == 2
