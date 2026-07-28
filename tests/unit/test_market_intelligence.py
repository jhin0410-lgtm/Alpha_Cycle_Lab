"""Tests for technical features and immutable intelligence snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.technical import (
    TechnicalFeatures,
    add_relative_strength_ranks,
    calculate_technical_features,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice

NOW = datetime(2026, 7, 28, 3, 30, tzinfo=UTC)


def _candles(symbol: str, *, slope: int = 1, count: int = 25) -> tuple[Candle, ...]:
    rows: list[Candle] = []
    for index in range(count):
        close = Decimal(str(100 + slope * index))
        rows.append(
            Candle(
                symbol=symbol,
                timestamp=NOW - timedelta(days=count - index),
                open_price=close,
                high_price=close + Decimal("1"),
                low_price=close - Decimal("1"),
                close_price=close,
                volume=Decimal(str(1000 + index * 10)),
                currency="KRW",
                interval="1d",
                adjusted=False,
            )
        )
    return tuple(rows)


def test_technical_features_are_explainable_and_null_when_unavailable() -> None:
    short = calculate_technical_features(_candles("AAA", count=3))
    assert short.return_1 is not None
    assert short.return_5 is None
    assert short.sma_20 is None
    assert short.rsi_14 is None

    full = calculate_technical_features(_candles("AAA"))
    assert full.observations == 25
    assert full.return_20 is not None and full.return_20 > 0
    assert full.price_to_sma_20 is not None and full.price_to_sma_20 > 0
    assert full.drawdown_from_20_high == 0
    assert full.rsi_14 == 100
    assert full.trend_efficiency_20 == 1
    assert full.trend_direction_20 == 1


def test_relative_strength_rank_is_cross_sectional() -> None:
    stronger = calculate_technical_features(_candles("AAA", slope=2))
    weaker = calculate_technical_features(_candles("BBB", slope=1))
    ranked = add_relative_strength_ranks((stronger, weaker))
    values = {item.symbol: item.relative_strength_rank_20 for item in ranked}
    assert values["AAA"] == 1.0
    assert values["BBB"] == 0.5


def test_snapshot_writer_is_content_addressed_and_idempotent(tmp_path) -> None:
    candles = _candles("AAA")
    features = calculate_technical_features(candles)
    snapshot = MarketIntelligenceSnapshot(
        captured_at=NOW,
        provider="tossinvest-readonly",
        interval="1d",
        adjusted=False,
        prices=(MarketPrice("AAA", NOW, Decimal("124"), "KRW"),),
        candles=candles,
        features=(features,),
        raw_prices={"result": [{"symbol": "AAA"}]},
        raw_candles={"AAA": {"result": {"candles": []}}},
    )
    first = write_market_intelligence_snapshot(tmp_path, snapshot)
    second = write_market_intelligence_snapshot(tmp_path, snapshot)
    assert first == second
    assert len(first) == 6
    manifest = json.loads(first[0].read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["order_api_enabled"] is False
    assert first[1].read_text(encoding="utf-8").splitlines()[0] == (
        "symbol,timestamp,last_price,currency"
    )


def test_snapshot_rejects_feature_symbol_mismatch() -> None:
    candles = _candles("AAA")
    wrong = TechnicalFeatures(
        symbol="BBB",
        interval="1d",
        adjusted=False,
        observations=1,
        last_price=1.0,
        return_1=None,
        return_5=None,
        return_20=None,
        sma_5=None,
        sma_20=None,
        price_to_sma_20=None,
        realized_volatility_20=None,
        volume_ratio_20=None,
        drawdown_from_20_high=None,
        rsi_14=None,
        trend_efficiency_20=None,
        trend_direction_20=None,
    )
    try:
        MarketIntelligenceSnapshot(
            captured_at=NOW,
            provider="tossinvest-readonly",
            interval="1d",
            adjusted=False,
            prices=(MarketPrice("AAA", NOW, Decimal("124"), "KRW"),),
            candles=candles,
            features=(wrong,),
            raw_prices={},
            raw_candles={},
        )
    except ValueError as exc:
        assert "feature symbols" in str(exc)
    else:
        raise AssertionError("Expected feature symbol mismatch")
