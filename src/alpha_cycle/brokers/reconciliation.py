"""Read-only broker snapshot reconciliation with fail-closed order gating."""

from __future__ import annotations

import csv
import json
import math
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

from alpha_cycle.paper import PaperTradingStore

ZERO = Decimal("0")
SNAPSHOT_SCHEMA_VERSION = 1
ACTIVE_LOCAL_STATUSES = {"pending", "partially_filled"}
ACTIVE_BROKER_STATUSES = {"open", "partially_filled"}


class ReconciliationSeverity(StrEnum):
    """Issue severity used by the order-submission safety gate."""

    WARNING = "warning"
    BLOCKING = "blocking"


class ReconciliationStatus(StrEnum):
    """Overall result of comparing local and broker state."""

    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class BrokerPosition:
    ticker: str
    quantity: int
    average_cost: Decimal | None = None


@dataclass(frozen=True)
class BrokerOrder:
    client_order_id: str
    broker_order_id: str
    ticker: str
    side: str
    quantity: int
    filled_quantity: int
    status: str


@dataclass(frozen=True)
class BrokerFill:
    fill_id: str
    client_order_id: str
    ticker: str
    side: str
    quantity: int
    price: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    schema_version: int
    broker: str
    account_ref_hash: str
    snapshot_id: str
    captured_at: datetime
    cash: Decimal
    positions: tuple[BrokerPosition, ...]
    open_orders: tuple[BrokerOrder, ...]
    fills: tuple[BrokerFill, ...]
    fill_history_complete: bool = False


@dataclass(frozen=True)
class LocalPosition:
    ticker: str
    quantity: int
    average_cost: Decimal


@dataclass(frozen=True)
class LocalOrderState:
    order_id: str
    ticker: str
    side: str
    quantity: int
    filled_quantity: int
    status: str


@dataclass(frozen=True)
class LocalAccountState:
    cash: Decimal
    positions: tuple[LocalPosition, ...]
    orders: tuple[LocalOrderState, ...]
    committed_fill_ids: frozenset[str]
    latest_session: date | None


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    severity: ReconciliationSeverity
    entity: str
    expected: str | None
    actual: str | None
    detail: str


@dataclass(frozen=True)
class ReconciliationReport:
    status: ReconciliationStatus
    can_submit_orders: bool
    snapshot_id: str
    captured_at: datetime
    snapshot_age_seconds: float
    issues: tuple[ReconciliationIssue, ...]

    @property
    def blocking_count(self) -> int:
        return sum(issue.severity is ReconciliationSeverity.BLOCKING for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity is ReconciliationSeverity.WARNING for issue in self.issues)


def _non_empty(value: object, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _decimal(value: object, field_name: str, *, minimum: Decimal = ZERO) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite() or result < minimum:
        raise ValueError(f"{field_name} must be finite and at least {minimum}")
    return result


def _integer(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if str(value).strip() not in {str(result), f"{result}.0"}:
        raise ValueError(f"{field_name} must be an exact integer")
    if result < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return result


def _aware_datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_account_ref_hash(value: object) -> str:
    text = _non_empty(value, "account_ref_hash").lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("account_ref_hash must be a SHA-256 hex digest, never a raw account number")
    return text


def _require_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def load_broker_snapshot(path: str | Path) -> BrokerAccountSnapshot:
    """Load and validate a read-only broker account snapshot JSON file."""
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"Broker snapshot does not exist: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Broker snapshot is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("Broker snapshot root must be an object")
    schema_version = _integer(raw.get("schema_version"), "schema_version", minimum=1)
    if schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported broker snapshot schema version: {schema_version}")

    positions: list[BrokerPosition] = []
    position_tickers: set[str] = set()
    for index, item in enumerate(_require_list(raw, "positions")):
        if not isinstance(item, dict):
            raise ValueError(f"positions[{index}] must be an object")
        ticker = _non_empty(item.get("ticker"), f"positions[{index}].ticker")
        if ticker in position_tickers:
            raise ValueError(f"Duplicate broker position ticker: {ticker}")
        position_tickers.add(ticker)
        average_cost_raw = item.get("average_cost")
        positions.append(
            BrokerPosition(
                ticker=ticker,
                quantity=_integer(item.get("quantity"), f"positions[{index}].quantity"),
                average_cost=(
                    _decimal(average_cost_raw, f"positions[{index}].average_cost")
                    if average_cost_raw is not None
                    else None
                ),
            )
        )

    orders: list[BrokerOrder] = []
    client_order_ids: set[str] = set()
    broker_order_ids: set[str] = set()
    for index, item in enumerate(_require_list(raw, "open_orders")):
        if not isinstance(item, dict):
            raise ValueError(f"open_orders[{index}] must be an object")
        client_order_id = _non_empty(
            item.get("client_order_id"), f"open_orders[{index}].client_order_id"
        )
        broker_order_id = _non_empty(
            item.get("broker_order_id"), f"open_orders[{index}].broker_order_id"
        )
        if client_order_id in client_order_ids:
            raise ValueError(f"Duplicate broker client_order_id: {client_order_id}")
        if broker_order_id in broker_order_ids:
            raise ValueError(f"Duplicate broker_order_id: {broker_order_id}")
        client_order_ids.add(client_order_id)
        broker_order_ids.add(broker_order_id)
        quantity = _integer(item.get("quantity"), f"open_orders[{index}].quantity", minimum=1)
        filled_quantity = _integer(
            item.get("filled_quantity"), f"open_orders[{index}].filled_quantity"
        )
        if filled_quantity > quantity:
            raise ValueError(f"open_orders[{index}].filled_quantity exceeds quantity")
        status = _non_empty(item.get("status"), f"open_orders[{index}].status").lower()
        if status not in ACTIVE_BROKER_STATUSES:
            raise ValueError(f"open_orders[{index}].status must be open or partially_filled")
        side = _non_empty(item.get("side"), f"open_orders[{index}].side").lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"open_orders[{index}].side must be buy or sell")
        orders.append(
            BrokerOrder(
                client_order_id=client_order_id,
                broker_order_id=broker_order_id,
                ticker=_non_empty(item.get("ticker"), f"open_orders[{index}].ticker"),
                side=side,
                quantity=quantity,
                filled_quantity=filled_quantity,
                status=status,
            )
        )

    fills: list[BrokerFill] = []
    fill_ids: set[str] = set()
    for index, item in enumerate(_require_list(raw, "fills")):
        if not isinstance(item, dict):
            raise ValueError(f"fills[{index}] must be an object")
        fill_id = _non_empty(item.get("fill_id"), f"fills[{index}].fill_id")
        if fill_id in fill_ids:
            raise ValueError(f"Duplicate broker fill_id: {fill_id}")
        fill_ids.add(fill_id)
        side = _non_empty(item.get("side"), f"fills[{index}].side").lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"fills[{index}].side must be buy or sell")
        fills.append(
            BrokerFill(
                fill_id=fill_id,
                client_order_id=_non_empty(
                    item.get("client_order_id"), f"fills[{index}].client_order_id"
                ),
                ticker=_non_empty(item.get("ticker"), f"fills[{index}].ticker"),
                side=side,
                quantity=_integer(item.get("quantity"), f"fills[{index}].quantity", minimum=1),
                price=_decimal(item.get("price"), f"fills[{index}].price", minimum=Decimal("0.00000001")),
                timestamp=_aware_datetime(item.get("timestamp"), f"fills[{index}].timestamp"),
            )
        )

    fill_history_complete = raw.get("fill_history_complete", False)
    if not isinstance(fill_history_complete, bool):
        raise ValueError("fill_history_complete must be boolean")
    return BrokerAccountSnapshot(
        schema_version=schema_version,
        broker=_non_empty(raw.get("broker"), "broker"),
        account_ref_hash=_validate_account_ref_hash(raw.get("account_ref_hash")),
        snapshot_id=_non_empty(raw.get("snapshot_id"), "snapshot_id"),
        captured_at=_aware_datetime(raw.get("captured_at"), "captured_at"),
        cash=_decimal(raw.get("cash"), "cash"),
        positions=tuple(sorted(positions, key=lambda item: item.ticker)),
        open_orders=tuple(sorted(orders, key=lambda item: item.client_order_id)),
        fills=tuple(sorted(fills, key=lambda item: item.fill_id)),
        fill_history_complete=fill_history_complete,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Paper audit file is missing: {path.name}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_local_account_state(audit_dir: str | Path) -> LocalAccountState:
    """Load normalized local account state exported by PaperTradingStore."""
    source = Path(audit_dir)
    metadata_path = source / "paper_metadata.json"
    if not metadata_path.is_file():
        raise ValueError("paper_metadata.json is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("paper_metadata.json root must be an object")
    integrity = metadata.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("ok") is not True:
        raise ValueError("Paper state integrity must pass before reconciliation")
    latest_session_raw = integrity.get("latest_session")
    latest_session = (
        date.fromisoformat(str(latest_session_raw)) if latest_session_raw is not None else None
    )

    checkpoint_rows = _read_csv(source / "paper_checkpoints.csv")
    if latest_session is None:
        run_metadata = metadata.get("metadata")
        if not isinstance(run_metadata, dict):
            raise ValueError("Paper run metadata is invalid")
        cash = _decimal(run_metadata.get("initial_cash"), "metadata.initial_cash")
        latest_checkpoint_rows: list[dict[str, str]] = []
    else:
        latest_checkpoint_rows = [
            row for row in checkpoint_rows if row.get("session_date") == latest_session.isoformat()
        ]
        if len(latest_checkpoint_rows) != 1:
            raise ValueError("Latest paper checkpoint is missing or duplicated")
        cash = _decimal(latest_checkpoint_rows[0].get("cash"), "paper cash")

    positions: list[LocalPosition] = []
    for row in _read_csv(source / "paper_positions.csv"):
        if latest_session is None or row.get("session_date") != latest_session.isoformat():
            continue
        positions.append(
            LocalPosition(
                ticker=_non_empty(row.get("ticker"), "paper position ticker"),
                quantity=_integer(row.get("quantity"), "paper position quantity"),
                average_cost=_decimal(row.get("average_cost"), "paper position average_cost"),
            )
        )

    latest_orders: dict[str, LocalOrderState] = {}
    for row in _read_csv(source / "paper_orders.csv"):
        order_id = _non_empty(row.get("order_id"), "paper order_id")
        latest_orders[order_id] = LocalOrderState(
            order_id=order_id,
            ticker=_non_empty(row.get("ticker"), "paper order ticker"),
            side=_non_empty(row.get("side"), "paper order side").lower(),
            quantity=_integer(row.get("quantity"), "paper order quantity", minimum=1),
            filled_quantity=_integer(row.get("filled_quantity"), "paper filled_quantity"),
            status=_non_empty(row.get("status"), "paper order status").lower(),
        )
    fill_ids = frozenset(
        _non_empty(row.get("fill_id"), "paper fill_id")
        for row in _read_csv(source / "paper_fills.csv")
    )
    return LocalAccountState(
        cash=cash,
        positions=tuple(sorted(positions, key=lambda item: item.ticker)),
        orders=tuple(latest_orders[key] for key in sorted(latest_orders)),
        committed_fill_ids=fill_ids,
        latest_session=latest_session,
    )


def local_state_from_store(store: PaperTradingStore) -> LocalAccountState:
    """Verify and export a paper store into an isolated temporary audit view."""
    store.assert_integrity()
    with tempfile.TemporaryDirectory(prefix="alpha-cycle-reconcile-") as temporary:
        store.export_audit(temporary)
        return load_local_account_state(temporary)


def _issue(
    issues: list[ReconciliationIssue],
    code: str,
    severity: ReconciliationSeverity,
    entity: str,
    expected: object | None,
    actual: object | None,
    detail: str,
) -> None:
    issues.append(
        ReconciliationIssue(
            code=code,
            severity=severity,
            entity=entity,
            expected=None if expected is None else str(expected),
            actual=None if actual is None else str(actual),
            detail=detail,
        )
    )


def reconcile_account_state(
    local: LocalAccountState,
    broker: BrokerAccountSnapshot,
    *,
    now: datetime | None = None,
    max_snapshot_age_seconds: int = 300,
    future_tolerance_seconds: int = 5,
    cash_tolerance: Decimal = ZERO,
    average_cost_tolerance: Decimal = Decimal("0.01"),
) -> ReconciliationReport:
    """Compare local paper state with one immutable broker snapshot."""
    if max_snapshot_age_seconds <= 0:
        raise ValueError("max_snapshot_age_seconds must be positive")
    if future_tolerance_seconds < 0:
        raise ValueError("future_tolerance_seconds cannot be negative")
    if cash_tolerance < ZERO or average_cost_tolerance < ZERO:
        raise ValueError("Reconciliation tolerances cannot be negative")
    evaluated_at = (now or datetime.now(UTC)).astimezone(UTC)
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    snapshot_age = (evaluated_at - broker.captured_at).total_seconds()
    if not math.isfinite(snapshot_age):
        raise ValueError("Snapshot age is not finite")

    issues: list[ReconciliationIssue] = []
    if snapshot_age < -future_tolerance_seconds:
        _issue(
            issues,
            "snapshot_from_future",
            ReconciliationSeverity.BLOCKING,
            "snapshot",
            f"<= {future_tolerance_seconds}s future skew",
            f"{snapshot_age:.3f}s",
            "Broker snapshot timestamp is ahead of the reconciliation clock.",
        )
    if snapshot_age > max_snapshot_age_seconds:
        _issue(
            issues,
            "stale_snapshot",
            ReconciliationSeverity.BLOCKING,
            "snapshot",
            f"<= {max_snapshot_age_seconds}s",
            f"{snapshot_age:.3f}s",
            "Broker snapshot is too old for order submission.",
        )
    if local.latest_session is not None and broker.captured_at.date() < local.latest_session:
        _issue(
            issues,
            "snapshot_precedes_local_state",
            ReconciliationSeverity.BLOCKING,
            "snapshot",
            local.latest_session,
            broker.captured_at.date(),
            "Broker snapshot predates the latest committed local session.",
        )

    if abs(local.cash - broker.cash) > cash_tolerance:
        _issue(
            issues,
            "cash_mismatch",
            ReconciliationSeverity.BLOCKING,
            "cash",
            local.cash,
            broker.cash,
            "Local and broker cash differ beyond the configured tolerance.",
        )

    local_positions = {item.ticker: item for item in local.positions if item.quantity != 0}
    broker_positions = {item.ticker: item for item in broker.positions if item.quantity != 0}
    for ticker in sorted(local_positions.keys() | broker_positions.keys()):
        local_position = local_positions.get(ticker)
        broker_position = broker_positions.get(ticker)
        if local_position is None:
            _issue(
                issues,
                "unexpected_broker_position",
                ReconciliationSeverity.BLOCKING,
                f"position:{ticker}",
                0,
                broker_position.quantity if broker_position else None,
                "Broker reports a position absent from local state.",
            )
            continue
        if broker_position is None:
            _issue(
                issues,
                "missing_broker_position",
                ReconciliationSeverity.BLOCKING,
                f"position:{ticker}",
                local_position.quantity,
                0,
                "Local state holds a position absent from the broker snapshot.",
            )
            continue
        if local_position.quantity != broker_position.quantity:
            _issue(
                issues,
                "position_quantity_mismatch",
                ReconciliationSeverity.BLOCKING,
                f"position:{ticker}",
                local_position.quantity,
                broker_position.quantity,
                "Share quantity mismatch requires reconciliation before new orders.",
            )
        if (
            broker_position.average_cost is not None
            and abs(local_position.average_cost - broker_position.average_cost)
            > average_cost_tolerance
        ):
            _issue(
                issues,
                "position_average_cost_mismatch",
                ReconciliationSeverity.WARNING,
                f"position:{ticker}",
                local_position.average_cost,
                broker_position.average_cost,
                "Average cost differs; fee and tax accounting may require review.",
            )

    local_orders = {item.order_id: item for item in local.orders}
    local_open_orders = {
        order_id: item
        for order_id, item in local_orders.items()
        if item.status in ACTIVE_LOCAL_STATUSES
    }
    broker_open_orders = {item.client_order_id: item for item in broker.open_orders}
    for order_id in sorted(local_open_orders.keys() | broker_open_orders.keys()):
        local_order = local_open_orders.get(order_id)
        broker_order = broker_open_orders.get(order_id)
        if local_order is None:
            _issue(
                issues,
                "unexpected_broker_open_order",
                ReconciliationSeverity.BLOCKING,
                f"order:{order_id}",
                None,
                broker_order.broker_order_id if broker_order else None,
                "Broker has an active order not represented in local state.",
            )
            continue
        if broker_order is None:
            _issue(
                issues,
                "missing_broker_open_order",
                ReconciliationSeverity.BLOCKING,
                f"order:{order_id}",
                local_order.status,
                None,
                "Local state has an active order absent from the broker snapshot.",
            )
            continue
        expected_status = "open" if local_order.status == "pending" else "partially_filled"
        comparisons = {
            "ticker": (local_order.ticker, broker_order.ticker),
            "side": (local_order.side, broker_order.side),
            "quantity": (local_order.quantity, broker_order.quantity),
            "filled_quantity": (local_order.filled_quantity, broker_order.filled_quantity),
            "status": (expected_status, broker_order.status),
        }
        for field_name, (expected, actual) in comparisons.items():
            if expected != actual:
                _issue(
                    issues,
                    f"open_order_{field_name}_mismatch",
                    ReconciliationSeverity.BLOCKING,
                    f"order:{order_id}",
                    expected,
                    actual,
                    f"Open order {field_name} differs between local and broker state.",
                )

    broker_fill_ids = {item.fill_id for item in broker.fills}
    for fill in broker.fills:
        if fill.fill_id not in local.committed_fill_ids:
            _issue(
                issues,
                "unrecorded_broker_fill",
                ReconciliationSeverity.BLOCKING,
                f"fill:{fill.fill_id}",
                "committed locally",
                "broker only",
                "Broker fill has not been committed to the local paper journal.",
            )
        if fill.client_order_id not in local_orders:
            _issue(
                issues,
                "fill_for_unknown_local_order",
                ReconciliationSeverity.BLOCKING,
                f"fill:{fill.fill_id}",
                "known local order",
                fill.client_order_id,
                "Broker fill references an order unknown to local state.",
            )
    if broker.fill_history_complete:
        for fill_id in sorted(local.committed_fill_ids - broker_fill_ids):
            _issue(
                issues,
                "missing_broker_fill",
                ReconciliationSeverity.BLOCKING,
                f"fill:{fill_id}",
                "present in complete broker history",
                "missing",
                "Complete broker fill history omits a locally committed fill.",
            )

    issues.sort(key=lambda item: (item.severity.value, item.code, item.entity))
    blocking = any(issue.severity is ReconciliationSeverity.BLOCKING for issue in issues)
    warning = any(issue.severity is ReconciliationSeverity.WARNING for issue in issues)
    status = (
        ReconciliationStatus.BLOCKED
        if blocking
        else ReconciliationStatus.REVIEW_REQUIRED
        if warning
        else ReconciliationStatus.READY
    )
    return ReconciliationReport(
        status=status,
        can_submit_orders=status is ReconciliationStatus.READY,
        snapshot_id=broker.snapshot_id,
        captured_at=broker.captured_at,
        snapshot_age_seconds=snapshot_age,
        issues=tuple(issues),
    )


def write_reconciliation_outputs(
    output_dir: str | Path,
    report: ReconciliationReport,
) -> tuple[Path, Path]:
    """Write deterministic JSON summary and normalized issue CSV."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    summary_path = destination / "reconciliation_report.json"
    issues_path = destination / "reconciliation_issues.csv"
    summary_path.write_text(
        json.dumps(
            {
                "status": report.status.value,
                "can_submit_orders": report.can_submit_orders,
                "snapshot_id": report.snapshot_id,
                "captured_at": report.captured_at.isoformat(),
                "snapshot_age_seconds": report.snapshot_age_seconds,
                "blocking_count": report.blocking_count,
                "warning_count": report.warning_count,
                "issues": [
                    {
                        **asdict(issue),
                        "severity": issue.severity.value,
                    }
                    for issue in report.issues
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with issues_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["code", "severity", "entity", "expected", "actual", "detail"],
        )
        writer.writeheader()
        for issue in report.issues:
            writer.writerow(
                {
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "entity": issue.entity,
                    "expected": issue.expected,
                    "actual": issue.actual,
                    "detail": issue.detail,
                }
            )
    return summary_path, issues_path
