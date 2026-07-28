"""Regression tests for fail-closed broker reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from alpha_cycle.brokers.reconciliation import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrder,
    BrokerPosition,
    LocalAccountState,
    LocalOrderState,
    LocalPosition,
    ReconciliationStatus,
    load_broker_snapshot,
    reconcile_account_state,
    write_reconciliation_outputs,
)

NOW = datetime(2026, 7, 28, 0, 0, tzinfo=UTC)


def _local() -> LocalAccountState:
    return LocalAccountState(
        cash=Decimal("900000"),
        positions=(LocalPosition("AAA", 10, Decimal("10000")),),
        orders=(
            LocalOrderState(
                order_id="O1",
                ticker="BBB",
                side="buy",
                quantity=5,
                filled_quantity=0,
                status="pending",
            ),
        ),
        committed_fill_ids=frozenset({"F1"}),
        latest_session=date(2026, 7, 28),
    )


def _broker(**overrides: object) -> BrokerAccountSnapshot:
    values: dict[str, object] = {
        "schema_version": 1,
        "broker": "synthetic",
        "account_ref_hash": "a" * 64,
        "snapshot_id": "S1",
        "captured_at": NOW,
        "cash": Decimal("900000"),
        "positions": (BrokerPosition("AAA", 10, Decimal("10000")),),
        "open_orders": (
            BrokerOrder(
                client_order_id="O1",
                broker_order_id="B1",
                ticker="BBB",
                side="buy",
                quantity=5,
                filled_quantity=0,
                status="open",
            ),
        ),
        "fills": (
            BrokerFill(
                fill_id="F1",
                client_order_id="O1",
                ticker="BBB",
                side="buy",
                quantity=1,
                price=Decimal("1000"),
                timestamp=NOW,
            ),
        ),
        "fill_history_complete": True,
    }
    values.update(overrides)
    return BrokerAccountSnapshot(**values)  # type: ignore[arg-type]


def test_matching_snapshot_is_ready() -> None:
    report = reconcile_account_state(_local(), _broker(), now=NOW)
    assert report.status is ReconciliationStatus.READY
    assert report.can_submit_orders is True
    assert report.issues == ()


def test_stale_and_future_snapshots_block() -> None:
    stale = reconcile_account_state(
        _local(),
        _broker(captured_at=NOW - timedelta(seconds=301)),
        now=NOW,
        max_snapshot_age_seconds=300,
    )
    future = reconcile_account_state(
        _local(),
        _broker(captured_at=NOW + timedelta(seconds=6)),
        now=NOW,
        future_tolerance_seconds=5,
    )
    assert stale.status is ReconciliationStatus.BLOCKED
    assert {issue.code for issue in stale.issues} == {"stale_snapshot"}
    assert future.status is ReconciliationStatus.BLOCKED
    assert {issue.code for issue in future.issues} == {"snapshot_from_future"}


def test_cash_and_position_quantity_mismatches_block() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(
            cash=Decimal("899999"),
            positions=(BrokerPosition("AAA", 9, Decimal("10000")),),
        ),
        now=NOW,
    )
    assert report.can_submit_orders is False
    assert {issue.code for issue in report.issues} == {
        "cash_mismatch",
        "position_quantity_mismatch",
    }


def test_unexpected_and_missing_positions_block() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(positions=(BrokerPosition("CCC", 2, Decimal("5000")),)),
        now=NOW,
    )
    assert {issue.code for issue in report.issues} == {
        "missing_broker_position",
        "unexpected_broker_position",
    }


def test_average_cost_difference_requires_review() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(positions=(BrokerPosition("AAA", 10, Decimal("10000.02")),)),
        now=NOW,
        average_cost_tolerance=Decimal("0.01"),
    )
    assert report.status is ReconciliationStatus.REVIEW_REQUIRED
    assert report.can_submit_orders is False
    assert [issue.code for issue in report.issues] == ["position_average_cost_mismatch"]


def test_open_order_mismatch_blocks() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(
            open_orders=(
                BrokerOrder("O1", "B1", "BBB", "buy", 5, 1, "partially_filled"),
            )
        ),
        now=NOW,
    )
    assert {issue.code for issue in report.issues} == {
        "open_order_filled_quantity_mismatch",
        "open_order_status_mismatch",
    }


def test_unrecorded_and_unknown_order_fill_blocks() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(
            fills=(
                BrokerFill("F2", "UNKNOWN", "BBB", "buy", 1, Decimal("1000"), NOW),
            ),
            fill_history_complete=False,
        ),
        now=NOW,
    )
    assert {issue.code for issue in report.issues} == {
        "fill_for_unknown_local_order",
        "unrecorded_broker_fill",
    }


def test_complete_fill_history_must_contain_local_fills() -> None:
    report = reconcile_account_state(
        _local(),
        _broker(fills=(), fill_history_complete=True),
        now=NOW,
    )
    assert [issue.code for issue in report.issues] == ["missing_broker_fill"]


def test_snapshot_loader_rejects_raw_account_number_and_duplicates(tmp_path) -> None:
    path = tmp_path / "snapshot.json"
    payload = {
        "schema_version": 1,
        "broker": "synthetic",
        "account_ref_hash": "12345678-01",
        "snapshot_id": "S1",
        "captured_at": NOW.isoformat(),
        "cash": "1000",
        "positions": [
            {"ticker": "AAA", "quantity": 1},
            {"ticker": "AAA", "quantity": 2},
        ],
        "open_orders": [],
        "fills": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_broker_snapshot(path)
    payload["account_ref_hash"] = "a" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate broker position"):
        load_broker_snapshot(path)


def test_reconciliation_outputs_are_deterministic(tmp_path) -> None:
    report = reconcile_account_state(
        _local(),
        _broker(cash=Decimal("899000")),
        now=NOW,
    )
    summary, issues = write_reconciliation_outputs(tmp_path, report)
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["can_submit_orders"] is False
    assert payload["blocking_count"] == 1
    lines = issues.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "code,severity,entity,expected,actual,detail"
    assert "cash_mismatch" in lines[1]
