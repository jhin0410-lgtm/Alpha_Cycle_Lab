from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from alpha_cycle.domain.models import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Side,
    TimeInForce,
)
from alpha_cycle.paper import PaperRunMetadata, PaperTradingStore
from alpha_cycle.portfolio.portfolio import Portfolio


def metadata() -> PaperRunMetadata:
    return PaperRunMetadata(
        run_id="paper-001",
        strategy_name="momentum",
        initial_cash=Decimal("1000000"),
        config_digest="config-sha256",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def filled_state(
    session: date = date(2024, 1, 2),
    *,
    order_id: str = "order-1",
    fill_id: str = "fill-1",
) -> tuple[Order, Fill, Portfolio]:
    order = Order(
        order_id=order_id,
        created_at=session,
        ticker="AAA",
        side=Side.BUY,
        quantity=10,
        reference_price=Decimal("100"),
        status=OrderStatus.FILLED,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        filled_quantity=10,
        last_attempt_at=session,
    )
    fill = Fill(
        order_id=order_id,
        fill_id=fill_id,
        timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc),
        ticker="AAA",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
        commission=Decimal("1"),
        tax=Decimal("0"),
        slippage=Decimal("0"),
    )
    portfolio = Portfolio(Decimal("1000000"))
    portfolio.apply_fill(fill)
    portfolio.mark({"AAA": Decimal("105")})
    return order, fill, portfolio


def test_commit_restore_and_identical_retry_are_deterministic(tmp_path) -> None:
    store = PaperTradingStore(tmp_path / "paper.sqlite")
    store.initialize(metadata())
    order, fill, portfolio = filled_state()

    first = store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )
    second = store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )

    assert first == second
    restored = store.restore_portfolio()
    assert restored.cash == portfolio.cash
    assert restored.positions["AAA"].quantity == 10
    assert restored.positions["AAA"].average_cost == Decimal("100.1")
    assert restored.last_prices["AAA"] == Decimal("105")
    report = store.assert_integrity()
    assert report.sessions == 1
    assert report.fills == 1


def test_conflicting_retry_and_out_of_order_session_are_rejected(tmp_path) -> None:
    store = PaperTradingStore(tmp_path / "paper.sqlite")
    store.initialize(metadata())
    order, fill, portfolio = filled_state()
    store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )

    with pytest.raises(ValueError, match="Conflicting state"):
        store.commit_session(
            date(2024, 1, 2),
            market_fingerprint="different-market-hash",
            orders=[order],
            fills=[fill],
            portfolio=portfolio,
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        store.commit_session(
            date(2024, 1, 1),
            market_fingerprint="market-hash-0",
            orders=[],
            fills=[],
            portfolio=Portfolio(Decimal("1000000")),
        )


def test_duplicate_fill_failure_is_atomic(tmp_path) -> None:
    store = PaperTradingStore(tmp_path / "paper.sqlite")
    store.initialize(metadata())
    order, fill, portfolio = filled_state()
    store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )
    order_2, duplicate_fill, portfolio_2 = filled_state(
        date(2024, 1, 3),
        order_id="order-2",
        fill_id="fill-1",
    )
    with pytest.raises(ValueError, match="Duplicate fill_id"):
        store.commit_session(
            date(2024, 1, 3),
            market_fingerprint="market-hash-2",
            orders=[order_2],
            fills=[duplicate_fill],
            portfolio=portfolio_2,
        )
    assert store.assert_integrity().sessions == 1


def test_restore_open_gtc_order(tmp_path) -> None:
    store = PaperTradingStore(tmp_path / "paper.sqlite")
    store.initialize(metadata())
    order = Order(
        order_id="gtc-1",
        created_at=date(2024, 1, 2),
        ticker="AAA",
        side=Side.BUY,
        quantity=20,
        reference_price=Decimal("100"),
        status=OrderStatus.PARTIALLY_FILLED,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        limit_price=Decimal("99"),
        filled_quantity=5,
        last_attempt_at=date(2024, 1, 2),
        last_attempt_reason="volume_limited",
    )
    store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[],
        portfolio=Portfolio(Decimal("1000000")),
    )

    restored = store.restore_open_orders()
    assert len(restored) == 1
    assert restored[0].order_id == "gtc-1"
    assert restored[0].remaining_quantity == 15


def test_integrity_detects_payload_tampering(tmp_path) -> None:
    database = tmp_path / "paper.sqlite"
    store = PaperTradingStore(database)
    store.initialize(metadata())
    order, fill, portfolio = filled_state()
    store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )
    with sqlite3.connect(database) as connection:
        payload = json.loads(
            connection.execute("SELECT payload_json FROM sessions").fetchone()[0]
        )
        payload["portfolio"]["cash"] = "999999"
        connection.execute(
            "UPDATE sessions SET payload_json = ?",
            (json.dumps(payload, sort_keys=True),),
        )

    report = store.verify_integrity()
    assert not report.ok
    assert any("Payload hash mismatch" in error for error in report.errors)
    with pytest.raises(ValueError, match="integrity failure"):
        store.export_audit(tmp_path / "audit")


def test_export_writes_normalized_audit_files(tmp_path) -> None:
    store = PaperTradingStore(tmp_path / "paper.sqlite")
    store.initialize(metadata())
    order, fill, portfolio = filled_state()
    store.commit_session(
        date(2024, 1, 2),
        market_fingerprint="market-hash-1",
        orders=[order],
        fills=[fill],
        portfolio=portfolio,
    )

    written = store.export_audit(tmp_path / "audit")
    assert {path.name for path in written} == {
        "paper_sessions.csv",
        "paper_orders.csv",
        "paper_fills.csv",
        "paper_checkpoints.csv",
        "paper_positions.csv",
        "paper_metadata.json",
    }
    metadata_payload = json.loads((tmp_path / "audit" / "paper_metadata.json").read_text())
    assert metadata_payload["integrity"]["ok"] is True
