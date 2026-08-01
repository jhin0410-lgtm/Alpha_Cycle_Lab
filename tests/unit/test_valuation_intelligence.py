"""Tests for valuation evidence, share-class completeness, and financial history."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.valuation import (
    CompanySecurityMapping,
    build_financial_history,
    build_valuation_evidence_snapshot,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_valuation import FinancialPeriodPayload, StockTotalsBatch


def _financial_row(
    statement: str,
    account_id: str,
    name: str,
    current: str,
    *,
    cumulative: str | None = None,
    prior: str = "80",
    prior_cumulative: str | None = None,
) -> dict[str, str]:
    row = {
        "sj_div": statement,
        "account_id": account_id,
        "account_nm": name,
        "account_detail": "-",
        "ord": "1",
        "thstrm_amount": current,
        "frmtrm_amount": prior,
        "frmtrm_q_amount": prior,
    }
    if cumulative is not None:
        row["thstrm_add_amount"] = cumulative
    if prior_cumulative is not None:
        row["frmtrm_add_amount"] = prior_cumulative
    return row


def _period(
    ticker: str,
    corp_code: str,
    year: int,
    report_code: str,
    period_end: date,
    available_date: date,
    rows: list[dict[str, str]],
) -> FinancialPeriodPayload:
    return FinancialPeriodPayload(
        ticker=ticker,
        corp_code=corp_code,
        business_year=year,
        report_code=report_code,
        period_end=period_end,
        available_date=available_date,
        payload={"status": "000", "list": rows},
    )


def _annual_period(ticker: str, corp_code: str, year: int, scale: int) -> FinancialPeriodPayload:
    return _period(
        ticker,
        corp_code,
        year,
        "11011",
        date(year, 12, 31),
        date(year + 1, 3, 15),
        [
            _financial_row("IS", "ifrs-full_Revenue", "Revenue", str(1000 * scale), prior="800"),
            _financial_row(
                "IS",
                "dart_OperatingIncomeLoss",
                "Operating income",
                str(200 * scale),
                prior="120",
            ),
            _financial_row(
                "IS", "ifrs-full_ProfitLoss", "Net income", str(150 * scale), prior="100"
            ),
            _financial_row("BS", "ifrs-full_Equity", "Equity", str(800 * scale), prior="700"),
            _financial_row(
                "BS", "ifrs-full_Liabilities", "Liabilities", str(300 * scale), prior="280"
            ),
            _financial_row(
                "BS",
                "ifrs-full_CashAndCashEquivalents",
                "Cash",
                str(250 * scale),
                prior="200",
            ),
            _financial_row(
                "CF",
                "ifrs-full_CashFlowsFromUsedInOperatingActivities",
                "Operating cash flow",
                str(220 * scale),
                prior="180",
            ),
            _financial_row(
                "CF",
                "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                "Capex",
                str(70 * scale),
                prior="60",
            ),
        ],
    )


def test_build_financial_history_derives_q4_and_growth_acceleration() -> None:
    q3 = _period(
        "005930",
        "00126380",
        2025,
        "11014",
        date(2025, 9, 30),
        date(2025, 11, 14),
        [
            _financial_row(
                "IS",
                "ifrs-full_Revenue",
                "Revenue",
                "40",
                cumulative="100",
                prior="30",
                prior_cumulative="80",
            ),
            _financial_row(
                "IS",
                "dart_OperatingIncomeLoss",
                "Operating income",
                "8",
                cumulative="20",
                prior="5",
                prior_cumulative="12",
            ),
            _financial_row(
                "IS",
                "ifrs-full_ProfitLoss",
                "Net income",
                "6",
                cumulative="15",
                prior="4",
                prior_cumulative="10",
            ),
        ],
    )
    fiscal = _period(
        "005930",
        "00126380",
        2025,
        "11011",
        date(2025, 12, 31),
        date(2026, 3, 15),
        [
            _financial_row("IS", "ifrs-full_Revenue", "Revenue", "150", prior="120"),
            _financial_row(
                "IS", "dart_OperatingIncomeLoss", "Operating income", "32", prior="20"
            ),
            _financial_row("IS", "ifrs-full_ProfitLoss", "Net income", "24", prior="16"),
            _financial_row("BS", "ifrs-full_Equity", "Equity", "100", prior="90"),
        ],
    )
    q1 = _period(
        "005930",
        "00126380",
        2026,
        "11013",
        date(2026, 3, 31),
        date(2026, 5, 15),
        [
            _financial_row(
                "IS",
                "ifrs-full_Revenue",
                "Revenue",
                "60",
                cumulative="60",
                prior="45",
                prior_cumulative="45",
            ),
            _financial_row(
                "IS",
                "dart_OperatingIncomeLoss",
                "Operating income",
                "15",
                cumulative="15",
                prior="10",
                prior_cumulative="10",
            ),
            _financial_row(
                "IS",
                "ifrs-full_ProfitLoss",
                "Net income",
                "11",
                cumulative="11",
                prior="8",
                prior_cumulative="8",
            ),
        ],
    )
    history = build_financial_history((q3, fiscal, q1))
    q4 = history.loc[history["period_label"] == "Q4"].iloc[0]
    assert q4["revenue"] == 50
    assert q4["revenue_prior_same"] == 40
    assert q4["operating_income"] == 12
    assert q4["derived"]
    latest_q1 = history.loc[
        (history["business_year"] == 2026) & (history["period_label"] == "Q1")
    ].iloc[0]
    assert latest_q1["revenue_yoy"] > 0.30
    assert pd.notna(latest_q1["operating_income_yoy_acceleration"])


class FakeValuationClient:
    def __init__(self, share_frames: dict[str, pd.DataFrame], periods: dict[str, tuple[FinancialPeriodPayload, ...]]) -> None:
        self.share_frames = share_frames
        self.periods = periods

    def latest_stock_totals(self, corp: CorpCode, *, evaluation_date: date) -> StockTotalsBatch:
        assert evaluation_date == date(2026, 7, 29)
        return StockTotalsBatch(
            self.share_frames[corp.stock_code].copy(),
            {"status": "000", "ticker": corp.stock_code},
            corp,
        )

    def financial_history_payloads(
        self,
        corp: CorpCode,
        *,
        evaluation_date: date,
        history_years: int,
        fs_div: str,
    ) -> tuple[FinancialPeriodPayload, ...]:
        assert evaluation_date == date(2026, 7, 29)
        assert history_years == 3
        assert fs_div == "CFS"
        return self.periods[corp.stock_code]


def _share_frame(ticker: str, corp_code: str, rows: list[tuple[str, str, int]]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for name, security_class, issued in rows:
        records.append(
            {
                "ticker": ticker,
                "corp_code": corp_code,
                "corp_name": ticker,
                "business_year": 2026,
                "report_code": "11013",
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "receipt_no": "20260515000001",
                "security_name": name,
                "security_class": security_class,
                "authorized_shares": None,
                "shares_issued_to_date": issued,
                "shares_reduced_to_date": 0,
                "issued_shares": issued,
                "treasury_shares": 0,
                "floating_shares": issued,
            }
        )
    return pd.DataFrame(records)


def _source_snapshots(root: Path, *, include_preferred_price: bool) -> tuple[Path, Path]:
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
        json.dumps(
            {
                "snapshot_id": market_id,
                "captured_at": "2026-07-28T05:18:27+00:00",
            }
        ),
        encoding="utf-8",
    )
    (research / "raw_opendart.json").write_text(
        json.dumps(
            {
                "005930": {
                    "corp": {
                        "corp_code": "00126380",
                        "corp_name": "Samsung",
                        "stock_code": "005930",
                        "modify_date": "2026-07-01",
                    }
                },
                "000660": {
                    "corp": {
                        "corp_code": "00164779",
                        "corp_name": "SK Hynix",
                        "stock_code": "000660",
                        "modify_date": "2026-07-01",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    prices = [
        {
            "symbol": "005930",
            "timestamp": "2026-07-28T05:00:00+00:00",
            "last_price": 100,
            "currency": "KRW",
        },
        {
            "symbol": "000660",
            "timestamp": "2026-07-28T05:00:00+00:00",
            "last_price": 200,
            "currency": "KRW",
        },
    ]
    if include_preferred_price:
        prices.append(
            {
                "symbol": "005935",
                "timestamp": "2026-07-28T05:00:00+00:00",
                "last_price": 80,
                "currency": "KRW",
            }
        )
    pd.DataFrame(prices).to_csv(market / "prices.csv", index=False)
    return research, market


def _fake_client() -> FakeValuationClient:
    shares = {
        "005930": _share_frame(
            "005930",
            "00126380",
            [("보통주", "common", 100), ("우선주", "preferred", 10), ("합계", "total", 110)],
        ),
        "000660": _share_frame(
            "000660",
            "00164779",
            [("보통주", "common", 50), ("합계", "total", 50)],
        ),
    }
    periods = {
        "005930": (_annual_period("005930", "00126380", 2025, 1),),
        "000660": (_annual_period("000660", "00164779", 2025, 2),),
    }
    return FakeValuationClient(shares, periods)


def test_valuation_snapshot_requires_prices_for_every_equity_class(tmp_path: Path) -> None:
    research, market = _source_snapshots(tmp_path, include_preferred_price=False)
    snapshot = build_valuation_evidence_snapshot(
        research,
        market,
        _fake_client(),  # type: ignore[arg-type]
        security_mappings={
            "005930": CompanySecurityMapping({"보통주": "005930", "우선주": "005935"})
        },
        now=datetime(2026, 7, 29, 4, tzinfo=UTC),
    )
    metrics = snapshot.valuation_metrics.set_index("ticker")
    assert not bool(metrics.loc["005930", "market_cap_complete"])
    assert pd.isna(metrics.loc["005930", "pe"])
    assert metrics.loc["005930", "valuation_status"] == "partial_market_cap"
    assert bool(metrics.loc["000660", "market_cap_complete"])
    assert snapshot.valuation_metrics["valuation_score"].isna().all()


def test_complete_security_prices_enable_peer_relative_valuation_and_write(tmp_path: Path) -> None:
    research, market = _source_snapshots(tmp_path, include_preferred_price=True)
    snapshot = build_valuation_evidence_snapshot(
        research,
        market,
        _fake_client(),  # type: ignore[arg-type]
        security_mappings={
            "005930": CompanySecurityMapping({"보통주": "005930", "우선주": "005935"})
        },
        now=datetime(2026, 7, 29, 4, tzinfo=UTC),
    )
    metrics = snapshot.valuation_metrics.set_index("ticker")
    assert bool(metrics.loc["005930", "market_cap_complete"])
    assert metrics.loc["005930", "market_cap"] == 10800
    assert metrics.loc["005930", "pe"] == 72
    assert snapshot.valuation_metrics["valuation_score"].notna().all()
    written = write_valuation_evidence_snapshot(tmp_path / "valuation", snapshot)
    assert len(written) == 6
    manifest = json.loads(written[0].read_text(encoding="utf-8"))
    assert manifest["market_cap_complete_count"] == 2
    assert manifest["valuation_scored_count"] == 2
    assert manifest["order_api_enabled"] is False
