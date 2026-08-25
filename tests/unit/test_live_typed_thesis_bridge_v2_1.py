from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence.decision_thesis_v2 import EpistemicStatus, ThesisStatus
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.technical import calculate_technical_features
from alpha_cycle.live_typed_source_manifest_v2_1 import freeze_live_typed_source_manifest
from alpha_cycle.live_typed_thesis_bridge_v2_1 import produce_source_backed_theses
from alpha_cycle.providers.tossinvest import Candle, MarketPrice


def _persist_sources(
    root: Path,
    *,
    research_market_snapshot_id: str | None = None,
) -> tuple[Path, Path, datetime]:
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    prices = (
        MarketPrice("000660", captured_at - timedelta(minutes=1), Decimal("250000"), "KRW"),
        MarketPrice("005930", captured_at - timedelta(minutes=1), Decimal("80000"), "KRW"),
    )
    candles: list[Candle] = []
    features = []
    for symbol, base in (("000660", Decimal("200000")), ("005930", Decimal("70000"))):
        symbol_candles = tuple(
            Candle(
                symbol=symbol,
                timestamp=captured_at - timedelta(days=21 - index),
                open_price=base + index - 1,
                high_price=base + index + 1,
                low_price=base + index - 2,
                close_price=base + index,
                volume=Decimal(1000 + index),
                currency="KRW",
                interval="1d",
                adjusted=True,
            )
            for index in range(21)
        )
        candles.extend(symbol_candles)
        features.append(calculate_technical_features(symbol_candles))
    market = MarketIntelligenceSnapshot(
        captured_at=captured_at,
        provider="tossinvest-readonly",
        interval="1d",
        adjusted=True,
        prices=prices,
        candles=tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp))),
        features=tuple(features),
        raw_prices={"source": "market"},
        raw_candles={"000660": {"count": 21}, "005930": {"count": 21}},
    )
    market_dir = write_market_intelligence_snapshot(root / "market", market)[0].parent

    financials = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "metric": metric,
                "period_end": "2025-12-31",
                "available_date": "2026-03-20",
                "value": value,
                "unit": "KRW",
            }
            for ticker, multiplier in (("000660", 2), ("005930", 1))
            for metric, value in (
                ("revenue", 1000 * multiplier),
                ("operating_income", 200 * multiplier),
            )
        ]
    )
    research = FundamentalMacroSnapshot(
        captured_at=captured_at + timedelta(minutes=5),
        evaluation_date=date(2026, 8, 25),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=financials,
        disclosures=pd.DataFrame(
            [
                {"ticker": "000660", "receipt_date": "2026-03-20", "rcept_no": "A"},
                {"ticker": "005930", "receipt_date": "2026-03-20", "rcept_no": "B"},
            ]
        ),
        macro=pd.DataFrame(
            [
                {
                    "series_id": "kr_base_rate",
                    "period_end": "2026-08-24",
                    "available_date": "2026-08-25",
                    "value": 2.5,
                }
            ]
        ),
        raw_opendart={"source": "opendart"},
        raw_ecos={"source": "ecos"},
        market_snapshot_id=(
            market.snapshot_id
            if research_market_snapshot_id is None
            else research_market_snapshot_id
        ),
    )
    research_dir = write_fundamental_macro_snapshot(root / "research", research)[0].parent
    return market_dir, research_dir, captured_at


def test_writer_backed_sources_produce_two_evidence_gated_theses(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    cutoff = captured_at + timedelta(minutes=20)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )

    receipt = produce_source_backed_theses(
        manifest,
        artifact_root=tmp_path,
        security_ids=("000660", "005930"),
        horizon_trading_days=126,
        captured_at=captured_at + timedelta(minutes=15),
    )

    assert not receipt.blockers
    assert tuple(item.security_id for item in receipt.theses) == ("000660", "005930")
    assert all(item.status is ThesisStatus.EVIDENCE_GATED for item in receipt.theses)
    assert all(item.captured_at <= cutoff for item in receipt.theses)
    assert all(
        claim.epistemic_status is EpistemicStatus.OBSERVED_FACT
        for thesis in receipt.theses
        for claim in thesis.claims
    )
    assert all(path.is_file() for path in receipt.thesis_paths)
    assert all(not thesis.catalysts for thesis in receipt.theses)
    assert all(not thesis.forecast_refs for thesis in receipt.theses)


def test_missing_official_financial_fact_becomes_structured_blocker(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    financials_path = research_dir / "financials.csv"
    financials = pd.read_csv(financials_path)
    financials = financials.loc[financials["ticker"].astype(str).str.zfill(6) != "005930"]
    financials.to_csv(financials_path, index=False)

    cutoff = captured_at + timedelta(minutes=20)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=cutoff,
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="canonical identity mismatch"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=126,
            captured_at=captured_at + timedelta(minutes=15),
        )


def test_mixed_market_research_generation_is_rejected(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(
        tmp_path,
        research_market_snapshot_id="f" * 64,
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="mixed source generations"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=126,
            captured_at=captured_at + timedelta(minutes=15),
        )


def test_future_market_observation_cannot_be_promoted(tmp_path: Path) -> None:
    market_dir, research_dir, captured_at = _persist_sources(tmp_path)
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market_dir, "research": research_dir},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(minutes=20),
        frozen_at=captured_at + timedelta(minutes=10),
    )
    prices_path = market_dir / "prices.csv"
    prices = pd.read_csv(prices_path)
    prices.loc[0, "timestamp"] = (captured_at + timedelta(hours=1)).isoformat()
    prices.to_csv(prices_path, index=False)

    with pytest.raises(ValueError, match="canonical identity mismatch"):
        produce_source_backed_theses(
            manifest,
            artifact_root=tmp_path,
            security_ids=("000660", "005930"),
            horizon_trading_days=126,
            captured_at=captured_at + timedelta(minutes=15),
        )
