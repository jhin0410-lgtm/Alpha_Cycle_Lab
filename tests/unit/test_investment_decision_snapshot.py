"""Integration tests for investment-decision snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import (
    CompanyExposure,
    DecisionPolicy,
    build_investment_decision_snapshot,
    write_investment_decision_snapshot,
)


def _row(statement: str, account_id: str, name: str, current: str, prior: str) -> dict[str, str]:
    return {
        "sj_div": statement,
        "account_id": account_id,
        "account_nm": name,
        "thstrm_amount": current,
        "frmtrm_amount": prior,
        "bfefrmtrm_amount": prior,
        "rcept_no": "20260315000001",
        "account_detail": "-",
        "ord": "1",
    }


def _write_source_snapshots(root: Path) -> tuple[Path, Path]:
    research = root / "research"
    market = root / "market"
    research.mkdir()
    market.mkdir()
    research_id = "a" * 64
    market_id = "b" * 64
    (research / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": research_id,
                "evaluation_date": "2026-07-29",
                "market_snapshot_id": market_id,
            }
        ),
        encoding="utf-8",
    )
    (market / "manifest.json").write_text(
        json.dumps({"snapshot_id": market_id}), encoding="utf-8"
    )
    financial_rows = [
        _row("IS", "ifrs-full_Revenue", "매출액", "120", "100"),
        _row("IS", "dart_OperatingIncomeLoss", "영업이익", "24", "10"),
        _row("IS", "ifrs-full_ProfitLoss", "당기순이익", "18", "9"),
        _row("BS", "ifrs-full_Assets", "자산총계", "300", "250"),
        _row("BS", "ifrs-full_Liabilities", "부채총계", "120", "110"),
        _row("BS", "ifrs-full_Equity", "자본총계", "180", "140"),
        _row(
            "CF",
            "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "영업활동현금흐름",
            "30",
            "20",
        ),
        _row(
            "CF",
            "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "유형자산의취득",
            "8",
            "7",
        ),
        _row("BS", "ifrs-full_CashAndCashEquivalents", "현금", "50", "45"),
        _row("BS", "ifrs-full_Inventories", "재고자산", "40", "30"),
        _row(
            "BS",
            "ifrs-full_TradeAndOtherCurrentReceivables",
            "매출채권",
            "20",
            "18",
        ),
    ]
    (research / "raw_opendart.json").write_text(
        json.dumps(
            {"005930": {"financial": {"financials": {"list": financial_rows}}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260728000001",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": "2026-07-28",
                "is_correction": False,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260728000002",
                "report_name": "임원ㆍ주요주주특정증권등소유상황보고서",
                "receipt_date": "2026-07-28",
                "is_correction": False,
            },
        ]
    ).to_csv(research / "disclosures.csv", index=False)
    macro_rows: list[dict[str, object]] = []
    for index, day in enumerate(pd.date_range("2026-07-01", periods=21, freq="D")):
        macro_rows.extend(
            [
                {
                    "series_id": "kr_base_rate",
                    "observation_date": day.date(),
                    "value": 2.5 if index < 10 else 2.25,
                    "unit": "%",
                },
                {
                    "series_id": "usd_krw",
                    "observation_date": day.date(),
                    "value": 1300 + index * 3,
                    "unit": "KRW/USD",
                },
            ]
        )
    pd.DataFrame(macro_rows).to_csv(research / "macro.csv", index=False)
    candle_rows: list[dict[str, object]] = []
    for index, day in enumerate(pd.date_range("2026-05-01", periods=70, freq="D")):
        price = 100 + index
        candle_rows.append(
            {
                "symbol": "005930",
                "timestamp": day.isoformat(),
                "open": price - 1,
                "high": price + 1,
                "low": price - 2,
                "close": price,
                "volume": 1000 + index,
            }
        )
    pd.DataFrame(candle_rows).to_csv(market / "candles.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "005930",
                "rsi_14": 60,
                "trend_efficiency_20": 0.9,
                "trend_direction_20": 1,
            }
        ]
    ).to_csv(market / "technical_features.csv", index=False)
    return research, market


def _write_valuation_snapshot(
    root: Path,
    *,
    research_id: str = "a" * 64,
    market_id: str = "b" * 64,
) -> Path:
    valuation = root / "valuation"
    valuation.mkdir()
    (valuation / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "c" * 64,
                "evaluation_date": "2026-07-29",
                "research_snapshot_id": research_id,
                "market_snapshot_id": market_id,
                "warnings": ["peer-relative valuation"],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "valuation_score": 4.2,
                "valuation_status": "complete_peer_relative_scored",
                "market_cap": 100000,
                "market_cap_proxy": 100000,
                "pe": 10,
                "pb": 1.2,
                "ps": 2,
                "fcf_yield": 0.05,
            }
        ]
    ).to_csv(valuation / "valuation_metrics.csv", index=False)
    pd.DataFrame(
        [
            {
                "ticker": "005930",
                "business_year": 2026,
                "period_label": "Q1",
                "period_end": "2026-03-31",
                "revenue_yoy": 0.2,
                "operating_income_yoy": 0.3,
                "operating_income_yoy_acceleration": 0.1,
            }
        ]
    ).to_csv(valuation / "financial_history.csv", index=False)
    return valuation


def test_build_and_write_integrated_decision_snapshot(tmp_path: Path) -> None:
    research, market = _write_source_snapshots(tmp_path)
    snapshot = build_investment_decision_snapshot(
        research,
        market,
        exposures={
            "005930": CompanyExposure(
                sector="semiconductor",
                export_fx_sensitivity=0.7,
                rate_duration_sensitivity=0.4,
            )
        },
        policy=DecisionPolicy(minimum_coverage=0.5),
        now=datetime(2026, 7, 29, 3, tzinfo=UTC),
    )
    score = snapshot.scorecards.iloc[0]
    assert score["ticker"] == "005930"
    assert score["earnings_momentum_score"] >= 4.0
    assert score["valuation_status"] == "not_available"
    assert snapshot.valuation_snapshot_id is None
    assert "Alpha Cycle 투자 의사결정 리포트" in snapshot.report_markdown
    written = write_investment_decision_snapshot(tmp_path / "decisions", snapshot)
    assert len(written) == 13
    manifest = json.loads(written[0].read_text(encoding="utf-8"))
    assert manifest["valuation_available"] is False
    assert manifest["valuation_scored_count"] == 0
    assert manifest["order_api_enabled"] is False
    assert (written[0].parent / "valuation_metrics.csv").is_file()
    assert (written[0].parent / "financial_history.csv").is_file()
    assert (written[0].parent / "scorecards.csv").is_file()
    assert (written[0].parent / "report.md").is_file()


def test_connected_valuation_updates_score_and_report(tmp_path: Path) -> None:
    research, market = _write_source_snapshots(tmp_path)
    valuation = _write_valuation_snapshot(tmp_path)
    baseline = build_investment_decision_snapshot(
        research,
        market,
        policy=DecisionPolicy(minimum_coverage=0.5),
        now=datetime(2026, 7, 29, 3, tzinfo=UTC),
    )
    snapshot = build_investment_decision_snapshot(
        research,
        market,
        valuation_snapshot=valuation,
        policy=DecisionPolicy(minimum_coverage=0.5),
        now=datetime(2026, 7, 29, 3, tzinfo=UTC),
    )
    score = snapshot.scorecards.iloc[0]
    assert snapshot.valuation_snapshot_id == "c" * 64
    assert score["valuation_score"] == 4.2
    assert score["score_coverage"] > baseline.scorecards.iloc[0]["score_coverage"]
    assert "밸류에이션 연결·컨센서스 미연결" in snapshot.report_markdown
    assert "밸류에이션·컨센서스 미연결 시" not in snapshot.report_markdown


def test_rejects_mismatched_valuation_source_snapshot(tmp_path: Path) -> None:
    research, market = _write_source_snapshots(tmp_path)
    valuation = _write_valuation_snapshot(tmp_path, market_id="d" * 64)
    try:
        build_investment_decision_snapshot(
            research,
            market,
            valuation_snapshot=valuation,
        )
    except ValueError as exc:
        assert "different market snapshot" in str(exc)
    else:
        raise AssertionError("Expected mismatched valuation snapshot rejection")


def test_rejects_mismatched_linked_market_snapshot(tmp_path: Path) -> None:
    research, market = _write_source_snapshots(tmp_path)
    manifest_path = research / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["market_snapshot_id"] = "c" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    try:
        build_investment_decision_snapshot(research, market)
    except ValueError as exc:
        assert "different market snapshot" in str(exc)
    else:
        raise AssertionError("Expected mismatched snapshot rejection")
