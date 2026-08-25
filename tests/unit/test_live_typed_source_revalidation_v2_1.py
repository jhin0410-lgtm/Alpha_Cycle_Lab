from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.data.research import (
    RevisionPolicy,
    validate_financial_statements,
    validate_macro_series,
)
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroSnapshot,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.technical import calculate_technical_features
from alpha_cycle.live_typed_source_revalidation_v2_1 import (
    LiveTypedSourceRevalidationError,
    revalidate_market_snapshot,
    revalidate_research_snapshot,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice


def _market_snapshot() -> MarketIntelligenceSnapshot:
    captured_at = datetime(2026, 8, 25, 6, 30, tzinfo=UTC)
    prices = (
        MarketPrice(
            symbol="000660",
            timestamp=captured_at - timedelta(minutes=1),
            last_price=Decimal("250000"),
            currency="KRW",
        ),
        MarketPrice(
            symbol="005930",
            timestamp=captured_at - timedelta(minutes=1),
            last_price=Decimal("80000"),
            currency="KRW",
        ),
    )
    candles: list[Candle] = []
    for symbol, base in (("000660", Decimal("200000")), ("005930", Decimal("70000"))):
        for index in range(21):
            close = base + Decimal(index * 100)
            candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=captured_at - timedelta(days=21 - index),
                    open_price=close - Decimal("20"),
                    high_price=close + Decimal("50"),
                    low_price=close - Decimal("50"),
                    close_price=close,
                    volume=Decimal(1000 + index),
                    currency="KRW",
                    interval="1d",
                    adjusted=True,
                )
            )
    ordered = tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp)))
    features = tuple(
        calculate_technical_features(tuple(item for item in ordered if item.symbol == symbol))
        for symbol in ("000660", "005930")
    )
    return MarketIntelligenceSnapshot(
        captured_at=captured_at,
        provider="tossinvest-readonly",
        interval="1d",
        adjusted=True,
        prices=prices,
        candles=ordered,
        features=features,
        raw_prices={"result": "market"},
        raw_candles={"000660": {"rows": 21}, "005930": {"rows": 21}},
    )


def _research_snapshot(market_snapshot_id: str) -> FundamentalMacroSnapshot:
    captured_at = datetime(2026, 8, 25, 6, 35, tzinfo=UTC)
    financials = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "metric": metric,
                "period_end": "2025-12-31",
                "fiscal_period": "FY",
                "available_date": "2026-03-20",
                "retrieved_at": "2026-08-25T06:35:00+00:00",
                "source": "opendart",
                "revision_id": f"{ticker}-{metric}-2025",
                "revision_sequence": 0,
                "value": value,
                "unit": "KRW",
            }
            for ticker, scale in (("000660", 2), ("005930", 1))
            for metric, value in (
                ("revenue", 1000 * scale),
                ("operating_income", 200 * scale),
            )
        ]
    )
    disclosures = pd.DataFrame(
        [
            {"ticker": "000660", "receipt_date": "2026-03-20", "rcept_no": "A"},
            {"ticker": "005930", "receipt_date": "2026-03-20", "rcept_no": "B"},
        ]
    )
    macro = validate_macro_series(pd.DataFrame(
        [
            {
                "series_id": "kr_base_rate",
                "observation_date": "2026-08-24",
                "frequency": "D",
                "available_date": "2026-08-25",
                "retrieved_at": "2026-08-25T06:35:00+00:00",
                "source": "ecos",
                "revision_id": "kr-base-rate-20260824",
                "revision_sequence": 0,
                "value": 2.5,
                "unit": "%",
            }
        ]
    ))
    return FundamentalMacroSnapshot(
        captured_at=captured_at,
        evaluation_date=date(2026, 8, 25),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
        financials=validate_financial_statements(financials),
        disclosures=disclosures,
        macro=macro,
        raw_opendart={"source": "opendart"},
        raw_ecos={"source": "ecos"},
        market_snapshot_id=market_snapshot_id,
        warnings=("fixture-warning",),
    )


def test_market_writer_round_trips_through_canonical_revalidation(tmp_path: Path) -> None:
    snapshot = _market_snapshot()
    files = write_market_intelligence_snapshot(tmp_path / "market", snapshot)

    replayed = revalidate_market_snapshot(files[0].parent)

    assert replayed.snapshot_id == snapshot.snapshot_id
    assert replayed == snapshot


def test_market_revalidation_preserves_writer_tuple_order(tmp_path: Path) -> None:
    original = _market_snapshot()
    snapshot = replace(
        original,
        candles=tuple(reversed(original.candles)),
    )
    files = write_market_intelligence_snapshot(tmp_path / "market", snapshot)

    replayed = revalidate_market_snapshot(files[0].parent)

    assert replayed.snapshot_id == snapshot.snapshot_id
    assert replayed == snapshot


def test_research_writer_round_trips_through_canonical_revalidation(tmp_path: Path) -> None:
    market = _market_snapshot()
    snapshot = _research_snapshot(market.snapshot_id)
    files = write_fundamental_macro_snapshot(tmp_path / "research", snapshot)

    replayed = revalidate_research_snapshot(files[0].parent)

    assert replayed.snapshot_id == snapshot.snapshot_id
    assert replayed.payload_without_id() == snapshot.payload_without_id()


def test_research_pit_uses_korean_source_civil_date(tmp_path: Path) -> None:
    market = _market_snapshot()
    original = _research_snapshot(market.snapshot_id)
    financials = original.financials.copy()
    financials["available_date"] = date(2026, 8, 25)
    financials["retrieved_at"] = pd.Timestamp("2026-08-24T20:59:00+00:00")
    macro = original.macro.copy()
    macro["available_date"] = date(2026, 8, 25)
    macro["retrieved_at"] = pd.Timestamp("2026-08-24T20:59:00+00:00")
    snapshot = replace(
        original,
        captured_at=datetime(2026, 8, 24, 21, 0, tzinfo=UTC),
        financials=financials,
        macro=macro,
    )
    files = write_fundamental_macro_snapshot(tmp_path / "research", snapshot)

    replayed = revalidate_research_snapshot(files[0].parent)

    assert replayed.snapshot_id == snapshot.snapshot_id


def test_research_revalidation_preserves_round_trip_float_identity(tmp_path: Path) -> None:
    market = _market_snapshot()
    original = _research_snapshot(market.snapshot_id)
    financials = original.financials.copy()
    financials["value"] = financials["value"].astype(float)
    financials.loc[0, "value"] = 0.08845845059190371
    macro = original.macro.copy()
    macro.loc[0, "value"] = 0.08845845059190371
    snapshot = replace(original, financials=financials, macro=macro)
    files = write_fundamental_macro_snapshot(tmp_path / "research", snapshot)

    replayed = revalidate_research_snapshot(files[0].parent)

    assert replayed.snapshot_id == snapshot.snapshot_id


def test_market_revalidation_rejects_self_declared_forged_snapshot_id(tmp_path: Path) -> None:
    snapshot = _market_snapshot()
    files = write_market_intelligence_snapshot(tmp_path / "market", snapshot)
    directory = files[0].parent
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["snapshot_id"] = "f" * 64
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(LiveTypedSourceRevalidationError, match="canonical identity mismatch"):
        revalidate_market_snapshot(directory)


def test_research_revalidation_rejects_modified_persisted_fact(tmp_path: Path) -> None:
    market = _market_snapshot()
    snapshot = _research_snapshot(market.snapshot_id)
    files = write_fundamental_macro_snapshot(tmp_path / "research", snapshot)
    directory = files[0].parent
    financials = pd.read_csv(directory / "financials.csv")
    financials.loc[0, "value"] = 999999
    financials.to_csv(directory / "financials.csv", index=False)

    with pytest.raises(LiveTypedSourceRevalidationError, match="canonical identity mismatch"):
        revalidate_research_snapshot(directory)


def test_research_revalidation_rejects_malformed_csv(tmp_path: Path) -> None:
    market = _market_snapshot()
    snapshot = _research_snapshot(market.snapshot_id)
    files = write_fundamental_macro_snapshot(tmp_path / "research", snapshot)
    directory = files[0].parent
    (directory / "financials.csv").write_text('ticker,metric\n"unterminated', encoding="utf-8")

    with pytest.raises(LiveTypedSourceRevalidationError, match="cannot decode snapshot CSV"):
        revalidate_research_snapshot(directory)
