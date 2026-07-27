"""Transactional SQLite state store for reproducible local paper-trading research."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpha_cycle.domain.models import Fill, Order, OrderStatus, OrderType, Side, TimeInForce
from alpha_cycle.portfolio.portfolio import Portfolio, Position

SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash an exact local market snapshot or configuration file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"File does not exist: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PaperRunMetadata:
    """Immutable identity for one paper-trading research run."""

    run_id: str
    strategy_name: str
    initial_cash: Decimal
    config_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("run_id", "strategy_name", "config_digest"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} cannot be empty")
            object.__setattr__(self, field_name, value)
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True)
class PositionSnapshot:
    ticker: str
    quantity: int
    average_cost: Decimal
    realized_pnl: Decimal
    last_price: Decimal | None


@dataclass(frozen=True)
class PaperCheckpoint:
    session_date: date
    sequence: int
    initial_cash: Decimal
    cash: Decimal
    total_commission: Decimal
    total_tax: Decimal
    total_slippage: Decimal
    traded_notional: Decimal
    positions: tuple[PositionSnapshot, ...]
    state_hash: str


@dataclass(frozen=True)
class IntegrityReport:
    ok: bool
    sessions: int
    order_states: int
    fills: int
    latest_session: date | None
    latest_hash: str | None
    errors: tuple[str, ...] = ()


def _order_to_dict(order: Order) -> dict[str, object]:
    return {
        "order_id": order.order_id,
        "created_at": order.created_at.isoformat(),
        "ticker": order.ticker,
        "side": order.side.value,
        "quantity": order.quantity,
        "reference_price": str(order.reference_price),
        "status": order.status.value,
        "rejection_reason": order.rejection_reason,
        "order_type": order.order_type.value,
        "time_in_force": order.time_in_force.value,
        "limit_price": str(order.limit_price) if order.limit_price is not None else None,
        "filled_quantity": order.filled_quantity,
        "last_attempt_at": (
            order.last_attempt_at.isoformat() if order.last_attempt_at is not None else None
        ),
        "last_attempt_reason": order.last_attempt_reason,
    }


def _order_from_dict(payload: dict[str, Any]) -> Order:
    limit_price = payload.get("limit_price")
    last_attempt = payload.get("last_attempt_at")
    return Order(
        order_id=str(payload["order_id"]),
        created_at=date.fromisoformat(str(payload["created_at"])),
        ticker=str(payload["ticker"]),
        side=Side(str(payload["side"])),
        quantity=int(payload["quantity"]),
        reference_price=Decimal(str(payload["reference_price"])),
        status=OrderStatus(str(payload["status"])),
        rejection_reason=(
            str(payload["rejection_reason"]) if payload.get("rejection_reason") is not None else None
        ),
        order_type=OrderType(str(payload["order_type"])),
        time_in_force=TimeInForce(str(payload["time_in_force"])),
        limit_price=Decimal(str(limit_price)) if limit_price is not None else None,
        filled_quantity=int(payload["filled_quantity"]),
        last_attempt_at=date.fromisoformat(str(last_attempt)) if last_attempt is not None else None,
        last_attempt_reason=(
            str(payload["last_attempt_reason"])
            if payload.get("last_attempt_reason") is not None
            else None
        ),
    )


def _fill_to_dict(fill: Fill) -> dict[str, object]:
    return {
        "fill_id": fill.fill_id,
        "order_id": fill.order_id,
        "timestamp": fill.timestamp.isoformat(),
        "ticker": fill.ticker,
        "side": fill.side.value,
        "quantity": fill.quantity,
        "price": str(fill.price),
        "commission": str(fill.commission),
        "tax": str(fill.tax),
        "slippage": str(fill.slippage),
    }


def _portfolio_to_dict(portfolio: Portfolio) -> dict[str, object]:
    positions = []
    for ticker, position in sorted(portfolio.positions.items()):
        last_price = portfolio.last_prices.get(ticker)
        positions.append(
            {
                "ticker": ticker,
                "quantity": position.quantity,
                "average_cost": str(position.average_cost),
                "realized_pnl": str(position.realized_pnl),
                "last_price": str(last_price) if last_price is not None else None,
            }
        )
    return {
        "initial_cash": str(portfolio.initial_cash),
        "cash": str(portfolio.cash),
        "total_commission": str(portfolio.total_commission),
        "total_tax": str(portfolio.total_tax),
        "total_slippage": str(portfolio.total_slippage),
        "traded_notional": str(portfolio.traded_notional),
        "positions": positions,
    }


class PaperTradingStore:
    """Append-only session journal with atomic commits and deterministic replay."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                session_date TEXT NOT NULL UNIQUE,
                market_fingerprint TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                state_hash TEXT NOT NULL UNIQUE,
                committed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS committed_fills (
                fill_id TEXT PRIMARY KEY,
                session_date TEXT NOT NULL,
                FOREIGN KEY (session_date) REFERENCES sessions(session_date) ON DELETE CASCADE
            );
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _metadata_dict(metadata: PaperRunMetadata) -> dict[str, str]:
        return {
            "schema_version": str(SCHEMA_VERSION),
            "run_id": metadata.run_id,
            "strategy_name": metadata.strategy_name,
            "initial_cash": str(metadata.initial_cash),
            "config_digest": metadata.config_digest,
            "created_at": metadata.created_at.astimezone(timezone.utc).isoformat(),
        }

    @staticmethod
    def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
        return {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key, value FROM metadata").fetchall()
        }

    @staticmethod
    def _require_initialized(connection: sqlite3.Connection) -> dict[str, str]:
        metadata = PaperTradingStore._read_metadata(connection)
        required = {
            "schema_version",
            "run_id",
            "strategy_name",
            "initial_cash",
            "config_digest",
            "created_at",
        }
        if not required.issubset(metadata):
            raise ValueError("Paper state database is not initialized")
        if metadata["schema_version"] != str(SCHEMA_VERSION):
            raise ValueError(
                f"Unsupported paper state schema version: {metadata['schema_version']}"
            )
        return metadata

    def initialize(self, metadata: PaperRunMetadata) -> None:
        """Create the database or verify immutable run identity."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        expected = self._metadata_dict(metadata)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._create_schema(connection)
            existing = self._read_metadata(connection)
            if not existing:
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    sorted(expected.items()),
                )
            else:
                immutable = (
                    "schema_version",
                    "run_id",
                    "strategy_name",
                    "initial_cash",
                    "config_digest",
                )
                conflicts = [key for key in immutable if existing.get(key) != expected[key]]
                if conflicts:
                    connection.rollback()
                    raise ValueError(
                        "Paper state metadata conflicts for: " + ", ".join(conflicts)
                    )
            connection.commit()

    @staticmethod
    def _validate_inputs(
        session_date: date,
        market_fingerprint: str,
        orders: Sequence[Order],
        fills: Sequence[Fill],
    ) -> None:
        if not market_fingerprint.strip():
            raise ValueError("market_fingerprint cannot be empty")
        order_ids = [order.order_id for order in orders]
        if any(not value.strip() for value in order_ids):
            raise ValueError("order_id cannot be empty")
        if len(order_ids) != len(set(order_ids)):
            raise ValueError("Duplicate order_id values in one session are not allowed")
        fill_ids = [fill.fill_id for fill in fills]
        if any(not value.strip() for value in fill_ids):
            raise ValueError("Paper trading fills require non-empty fill_id values")
        if len(fill_ids) != len(set(fill_ids)):
            raise ValueError("Duplicate fill_id values in one session are not allowed")
        order_map = {order.order_id: order for order in orders}
        for order in orders:
            if order.created_at > session_date:
                raise ValueError(f"Order {order.order_id} was created after the session")
            if order.last_attempt_at is not None and order.last_attempt_at > session_date:
                raise ValueError(f"Order {order.order_id} has a future last_attempt_at")
        for fill in fills:
            if fill.timestamp.tzinfo is None or fill.timestamp.utcoffset() is None:
                raise ValueError(f"Fill {fill.fill_id} timestamp must be timezone-aware")
            order = order_map.get(fill.order_id)
            if order is None:
                raise ValueError(
                    f"Fill {fill.fill_id} requires current state for order {fill.order_id}"
                )
            if order.ticker != fill.ticker or order.side is not fill.side:
                raise ValueError(f"Fill {fill.fill_id} does not match its order")

    @staticmethod
    def _payload(
        session_date: date,
        market_fingerprint: str,
        orders: Sequence[Order],
        fills: Sequence[Fill],
        portfolio: Portfolio,
    ) -> dict[str, object]:
        return {
            "session_date": session_date.isoformat(),
            "market_fingerprint": market_fingerprint,
            "orders": [_order_to_dict(item) for item in sorted(orders, key=lambda x: x.order_id)],
            "fills": [_fill_to_dict(item) for item in sorted(fills, key=lambda x: x.fill_id)],
            "portfolio": _portfolio_to_dict(portfolio),
        }

    def commit_session(
        self,
        session_date: date,
        *,
        market_fingerprint: str,
        orders: Sequence[Order],
        fills: Sequence[Fill],
        portfolio: Portfolio,
    ) -> PaperCheckpoint:
        """Atomically append one session; identical retries are idempotent."""
        self._validate_inputs(session_date, market_fingerprint, orders, fills)
        payload = self._payload(
            session_date,
            market_fingerprint.strip(),
            orders,
            fills,
            portfolio,
        )
        payload_json = _canonical_json(payload)
        payload_hash = _digest(payload_json)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            existing = connection.execute(
                "SELECT payload_hash FROM sessions WHERE session_date = ?",
                (session_date.isoformat(),),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != payload_hash:
                    connection.rollback()
                    raise ValueError(f"Conflicting state exists for session {session_date}")
                connection.commit()
                return self._checkpoint_from_payload(connection, session_date, payload)

            latest = connection.execute(
                "SELECT session_date, state_hash FROM sessions ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if latest is not None and date.fromisoformat(str(latest["session_date"])) >= session_date:
                connection.rollback()
                raise ValueError("Paper sessions must be committed in strictly increasing order")
            for fill in fills:
                if connection.execute(
                    "SELECT 1 FROM committed_fills WHERE fill_id = ?",
                    (fill.fill_id,),
                ).fetchone():
                    connection.rollback()
                    raise ValueError(f"Duplicate fill_id already committed: {fill.fill_id}")

            previous_hash = str(latest["state_hash"]) if latest is not None else GENESIS_HASH
            state_hash = _digest(previous_hash + payload_hash)
            connection.execute(
                """
                INSERT INTO sessions(
                    session_date, market_fingerprint, previous_hash, payload_json,
                    payload_hash, state_hash, committed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_date.isoformat(),
                    market_fingerprint.strip(),
                    previous_hash,
                    payload_json,
                    payload_hash,
                    state_hash,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO committed_fills(fill_id, session_date) VALUES (?, ?)",
                [(fill.fill_id, session_date.isoformat()) for fill in fills],
            )
            connection.commit()
            return self._checkpoint_from_payload(connection, session_date, payload)

    @staticmethod
    def _checkpoint_from_payload(
        connection: sqlite3.Connection,
        session_date: date,
        payload: dict[str, object],
    ) -> PaperCheckpoint:
        row = connection.execute(
            "SELECT sequence, state_hash FROM sessions WHERE session_date = ?",
            (session_date.isoformat(),),
        ).fetchone()
        if row is None:
            raise ValueError(f"Missing session checkpoint: {session_date}")
        portfolio = payload["portfolio"]
        if not isinstance(portfolio, dict):
            raise ValueError("Stored portfolio payload is invalid")
        raw_positions = portfolio.get("positions")
        if not isinstance(raw_positions, list):
            raise ValueError("Stored position payload is invalid")
        positions = tuple(
            PositionSnapshot(
                ticker=str(item["ticker"]),
                quantity=int(item["quantity"]),
                average_cost=Decimal(str(item["average_cost"])),
                realized_pnl=Decimal(str(item["realized_pnl"])),
                last_price=(
                    Decimal(str(item["last_price"]))
                    if item.get("last_price") is not None
                    else None
                ),
            )
            for item in raw_positions
            if isinstance(item, dict)
        )
        if len(positions) != len(raw_positions):
            raise ValueError("Stored position payload contains invalid rows")
        return PaperCheckpoint(
            session_date=session_date,
            sequence=int(row["sequence"]),
            initial_cash=Decimal(str(portfolio["initial_cash"])),
            cash=Decimal(str(portfolio["cash"])),
            total_commission=Decimal(str(portfolio["total_commission"])),
            total_tax=Decimal(str(portfolio["total_tax"])),
            total_slippage=Decimal(str(portfolio["total_slippage"])),
            traded_notional=Decimal(str(portfolio["traded_notional"])),
            positions=positions,
            state_hash=str(row["state_hash"]),
        )

    def latest_checkpoint(self) -> PaperCheckpoint | None:
        """Load the latest committed account checkpoint."""
        with self._connect() as connection:
            self._require_initialized(connection)
            row = connection.execute(
                """
                SELECT session_date, payload_json
                FROM sessions
                ORDER BY sequence DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            session_date = date.fromisoformat(str(row["session_date"]))
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise ValueError("Stored session payload is invalid")
            return self._checkpoint_from_payload(connection, session_date, payload)

    def restore_portfolio(self) -> Portfolio:
        """Restore cash, positions, marks, realized P&L, and cumulative costs."""
        checkpoint = self.latest_checkpoint()
        if checkpoint is None:
            with self._connect() as connection:
                metadata = self._require_initialized(connection)
            return Portfolio(Decimal(metadata["initial_cash"]))
        portfolio = Portfolio(checkpoint.initial_cash)
        portfolio.cash = checkpoint.cash
        portfolio.total_commission = checkpoint.total_commission
        portfolio.total_tax = checkpoint.total_tax
        portfolio.total_slippage = checkpoint.total_slippage
        portfolio.traded_notional = checkpoint.traded_notional
        for item in checkpoint.positions:
            portfolio.positions[item.ticker] = Position(
                ticker=item.ticker,
                quantity=item.quantity,
                average_cost=item.average_cost,
                realized_pnl=item.realized_pnl,
            )
            if item.last_price is not None:
                portfolio.last_prices[item.ticker] = item.last_price
        return portfolio

    def restore_open_orders(self) -> tuple[Order, ...]:
        """Restore the latest known state of every still-open order."""
        latest_by_id: dict[str, dict[str, Any]] = {}
        with self._connect() as connection:
            self._require_initialized(connection)
            rows = connection.execute(
                "SELECT payload_json FROM sessions ORDER BY sequence"
            ).fetchall()
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict) or not isinstance(payload.get("orders"), list):
                raise ValueError("Stored order payload is invalid")
            for item in payload["orders"]:
                if not isinstance(item, dict):
                    raise ValueError("Stored order row is invalid")
                latest_by_id[str(item["order_id"])] = item
        orders = tuple(_order_from_dict(latest_by_id[key]) for key in sorted(latest_by_id))
        return tuple(order for order in orders if order.is_open)

    def verify_integrity(self) -> IntegrityReport:
        """Verify session hashes, strict date order, and committed fill index."""
        errors: list[str] = []
        order_states = 0
        fill_ids: list[str] = []
        latest_session: date | None = None
        latest_hash: str | None = None
        with self._connect() as connection:
            try:
                self._require_initialized(connection)
            except ValueError as exc:
                return IntegrityReport(False, 0, 0, 0, None, None, (str(exc),))
            rows = connection.execute(
                """
                SELECT sequence, session_date, previous_hash, payload_json,
                       payload_hash, state_hash
                FROM sessions
                ORDER BY sequence
                """
            ).fetchall()
            expected_previous = GENESIS_HASH
            for expected_sequence, row in enumerate(rows, start=1):
                session_text = str(row["session_date"])
                session_date = date.fromisoformat(session_text)
                if int(row["sequence"]) != expected_sequence:
                    errors.append(f"Non-contiguous sequence at {session_text}")
                if latest_session is not None and session_date <= latest_session:
                    errors.append(f"Non-increasing session date at {session_text}")
                if str(row["previous_hash"]) != expected_previous:
                    errors.append(f"Broken previous_hash at {session_text}")
                payload_json = str(row["payload_json"])
                calculated_payload = _digest(payload_json)
                if calculated_payload != str(row["payload_hash"]):
                    errors.append(f"Payload hash mismatch at {session_text}")
                calculated_state = _digest(expected_previous + str(row["payload_hash"]))
                if calculated_state != str(row["state_hash"]):
                    errors.append(f"State hash mismatch at {session_text}")
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    errors.append(f"Invalid JSON payload at {session_text}")
                    payload = {}
                if not isinstance(payload, dict):
                    errors.append(f"Invalid payload object at {session_text}")
                    payload = {}
                orders = payload.get("orders", [])
                fills = payload.get("fills", [])
                if not isinstance(orders, list) or not isinstance(fills, list):
                    errors.append(f"Invalid order or fill collection at {session_text}")
                else:
                    order_states += len(orders)
                    for fill in fills:
                        if not isinstance(fill, dict) or not str(fill.get("fill_id", "")).strip():
                            errors.append(f"Invalid fill payload at {session_text}")
                        else:
                            fill_ids.append(str(fill["fill_id"]))
                expected_previous = str(row["state_hash"])
                latest_session = session_date
                latest_hash = expected_previous

            indexed = {
                str(row["fill_id"])
                for row in connection.execute(
                    "SELECT fill_id FROM committed_fills ORDER BY fill_id"
                ).fetchall()
            }
            if len(fill_ids) != len(set(fill_ids)):
                errors.append("Duplicate fill_id exists inside session payloads")
            if indexed != set(fill_ids):
                errors.append("Committed fill index does not match session payloads")
        return IntegrityReport(
            ok=not errors,
            sessions=len(rows),
            order_states=order_states,
            fills=len(fill_ids),
            latest_session=latest_session,
            latest_hash=latest_hash,
            errors=tuple(errors),
        )

    def assert_integrity(self) -> IntegrityReport:
        report = self.verify_integrity()
        if not report.ok:
            raise ValueError("Paper state integrity failure: " + "; ".join(report.errors))
        return report

    @staticmethod
    def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def export_audit(self, output_dir: str | Path) -> list[Path]:
        """Export sessions, order states, fills, checkpoints, positions, and metadata."""
        report = self.assert_integrity()
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        session_rows: list[dict[str, object]] = []
        order_rows: list[dict[str, object]] = []
        fill_rows: list[dict[str, object]] = []
        checkpoint_rows: list[dict[str, object]] = []
        position_rows: list[dict[str, object]] = []
        with self._connect() as connection:
            metadata = self._require_initialized(connection)
            rows = connection.execute(
                """
                SELECT sequence, session_date, market_fingerprint, previous_hash,
                       payload_json, payload_hash, state_hash, committed_at
                FROM sessions
                ORDER BY sequence
                """
            ).fetchall()
        for row in rows:
            session_date = str(row["session_date"])
            session_rows.append(
                {
                    "sequence": int(row["sequence"]),
                    "session_date": session_date,
                    "market_fingerprint": str(row["market_fingerprint"]),
                    "previous_hash": str(row["previous_hash"]),
                    "payload_hash": str(row["payload_hash"]),
                    "state_hash": str(row["state_hash"]),
                    "committed_at": str(row["committed_at"]),
                }
            )
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise ValueError(f"Stored payload is invalid for {session_date}")
            for order in payload.get("orders", []):
                if not isinstance(order, dict):
                    raise ValueError(f"Stored order is invalid for {session_date}")
                order_rows.append({"session_date": session_date, **order})
            for fill in payload.get("fills", []):
                if not isinstance(fill, dict):
                    raise ValueError(f"Stored fill is invalid for {session_date}")
                fill_rows.append({"session_date": session_date, **fill})
            portfolio = payload.get("portfolio")
            if not isinstance(portfolio, dict):
                raise ValueError(f"Stored portfolio is invalid for {session_date}")
            checkpoint_rows.append(
                {
                    "session_date": session_date,
                    **{key: value for key, value in portfolio.items() if key != "positions"},
                }
            )
            positions = portfolio.get("positions")
            if not isinstance(positions, list):
                raise ValueError(f"Stored positions are invalid for {session_date}")
            for position in positions:
                if not isinstance(position, dict):
                    raise ValueError(f"Stored position row is invalid for {session_date}")
                position_rows.append({"session_date": session_date, **position})

        files = [
            (
                "paper_sessions.csv",
                [
                    "sequence",
                    "session_date",
                    "market_fingerprint",
                    "previous_hash",
                    "payload_hash",
                    "state_hash",
                    "committed_at",
                ],
                session_rows,
            ),
            (
                "paper_orders.csv",
                [
                    "session_date",
                    "order_id",
                    "created_at",
                    "ticker",
                    "side",
                    "quantity",
                    "reference_price",
                    "status",
                    "rejection_reason",
                    "order_type",
                    "time_in_force",
                    "limit_price",
                    "filled_quantity",
                    "last_attempt_at",
                    "last_attempt_reason",
                ],
                order_rows,
            ),
            (
                "paper_fills.csv",
                [
                    "session_date",
                    "fill_id",
                    "order_id",
                    "timestamp",
                    "ticker",
                    "side",
                    "quantity",
                    "price",
                    "commission",
                    "tax",
                    "slippage",
                ],
                fill_rows,
            ),
            (
                "paper_checkpoints.csv",
                [
                    "session_date",
                    "initial_cash",
                    "cash",
                    "total_commission",
                    "total_tax",
                    "total_slippage",
                    "traded_notional",
                ],
                checkpoint_rows,
            ),
            (
                "paper_positions.csv",
                [
                    "session_date",
                    "ticker",
                    "quantity",
                    "average_cost",
                    "realized_pnl",
                    "last_price",
                ],
                position_rows,
            ),
        ]
        written: list[Path] = []
        for name, fields, values in files:
            path = destination / name
            self._write_csv(path, fields, values)
            written.append(path)

        metadata_path = destination / "paper_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "metadata": metadata,
                    "integrity": {
                        "ok": report.ok,
                        "sessions": report.sessions,
                        "order_states": report.order_states,
                        "fills": report.fills,
                        "latest_session": (
                            report.latest_session.isoformat()
                            if report.latest_session is not None
                            else None
                        ),
                        "latest_hash": report.latest_hash,
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        written.append(metadata_path)
        return written
