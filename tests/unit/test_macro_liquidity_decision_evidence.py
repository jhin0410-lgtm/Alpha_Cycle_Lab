from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.macro_liquidity_decision_evidence import (
    append_macro_liquidity_report,
    build_macro_liquidity_decision_evidence,
)
from alpha_cycle.intelligence.macro_liquidity_evidence import (
    build_macro_liquidity_evidence,
    load_macro_liquidity_registry,
)
from alpha_cycle.macro_liquidity_cli import write_macro_liquidity_evidence

REGISTRY = Path("config/macro_liquidity_sources.yaml")


def _csv(series_id: str, base: float) -> bytes:
    rows = [f"DATE,{series_id}"]
    for index in range(25):
        day = (pd.Timestamp("2026-07-01") + pd.Timedelta(days=index)).date().isoformat()
        rows.append(f"{day},{base + index}")
    return ("\n".join(rows) + "\n").encode()


def _pointer(tmp_path: Path, evaluation_date: date = date(2026, 8, 14)) -> Path:
    specs = load_macro_liquidity_registry(REGISTRY)
    bases = {
        "DFII10": 1.5,
        "DTWEXBGS": 120.0,
        "NFCI": -1.0,
        "WALCL": 6_700_000.0,
        "WRESBAL": 3_000_000.0,
    }
    payloads = {spec.url: _csv(spec.series_id, bases[spec.series_id]) for spec in specs}
    evidence = build_macro_liquidity_evidence(
        specs,
        lambda url: payloads[url],
        evaluation_date=evaluation_date,
    )
    output = tmp_path / "macro"
    write_macro_liquidity_evidence(
        evidence,
        output,
        registry_path=REGISTRY,
        captured_at=datetime(2026, 8, 14, 7, 0, tzinfo=UTC),
    )
    return output / "latest_macro_liquidity_evidence.json"


def _macro_regime() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series_id": "kr_base_rate",
                "latest_value": 2.75,
                "regime": "easing",
            },
            {
                "series_id": "usd_krw",
                "latest_value": 1433.6,
                "regime": "krw_weakening",
            },
        ]
    )


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "composite_score": 3.8,
                "valuation_score": pd.NA,
                "investor_flow_available": True,
                "investor_flow_evidence_verified": False,
            },
            {
                "ticker": "005930",
                "composite_score": 3.6,
                "valuation_score": pd.NA,
                "investor_flow_available": True,
                "investor_flow_evidence_verified": False,
            },
        ]
    )


def test_macro_liquidity_decision_map_keeps_legs_separate_and_non_scoring(
    tmp_path: Path,
) -> None:
    evidence = build_macro_liquidity_decision_evidence(
        _pointer(tmp_path),
        _macro_regime(),
        _scorecards(),
        evaluation_date=date(2026, 8, 14),
    )
    assert evidence.decision_score_enabled is False
    assert evidence.composite_liquidity_score_enabled is False
    assert evidence.forecast_enabled is False
    assert evidence.causal_claim_enabled is False
    assert evidence.point_in_time_backtest_eligible is False

    states = dict(zip(evidence.coverage["dimension"], evidence.coverage["status"], strict=True))
    assert states["us_real_discount_rate"] == "available"
    assert states["broad_us_dollar"] == "available"
    assert states["us_financial_conditions"] == "available"
    assert states["fed_balance_sheet"] == "partial"
    assert states["fed_reserve_balances"] == "partial"
    assert states["korea_policy_rate"] == "available"
    assert states["usd_krw"] == "available"
    assert states["korea_investor_flow"] == "partial"
    assert states["semiconductor_risk_appetite"] == "missing"

    report = append_macro_liquidity_report("# Base\n", evidence)
    assert "Macro / Liquidity Vertical v1 (비점수)" in report
    assert "순유동성" in report
    assert "semiconductor_risk_appetite" in report


def test_macro_liquidity_decision_rejects_stale_evaluation_date(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path, evaluation_date=date(2026, 8, 13))
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        build_macro_liquidity_decision_evidence(
            pointer,
            _macro_regime(),
            _scorecards(),
            evaluation_date=date(2026, 8, 14),
        )
