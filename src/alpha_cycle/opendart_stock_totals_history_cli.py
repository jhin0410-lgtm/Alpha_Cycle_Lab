"""Collect immutable period-specific OpenDART issued-share history.

The artifact is deliberately separate from live valuation.  It preserves each
report's receipt-derived availability date so later historical valuation work can
join an unadjusted market price only to share counts that had become observable
by that date.  The artifact alone is not decision-scoring or backtest-certified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping, Protocol
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.providers.opendart import CorpCode, OpenDartCredentials
from alpha_cycle.providers.opendart_valuation import (
    OpenDartValuationClient,
    StockTotalsBatch,
    _candidate_periods,
)

DEFAULT_LIVE_ROOT = Path("data/private/live-research")
DEFAULT_OUTPUT_ROOT = DEFAULT_LIVE_ROOT / "opendart-stock-totals-history"
LATEST_POINTER_NAME = "latest_opendart_stock_totals_history.json"
SCHEMA_VERSION = 1
SOURCE_SCOPE = "opendart_stockTotqySttus_period_history"


class StockTotalsHistoryClient(Protocol):
    def stock_totals(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
    ) -> StockTotalsBatch: ...


@dataclass(frozen=True)
class StockTotalsHistorySnapshot:
    captured_at: datetime
    evaluation_date: date
    research_snapshot_id: str
    history_years: int
    frame: pd.DataFrame
    raw_periods: Mapping[str, object]

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "stock_totals_history_captured",
            "source_scope": SOURCE_SCOPE,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_snapshot_id": self.research_snapshot_id,
            "history_years": self.history_years,
            "tickers": sorted(self.frame["ticker"].astype(str).unique().tolist()),
            "row_count": len(self.frame),
            "period_count": int(
                self.frame[["ticker", "business_year", "report_code"]]
                .drop_duplicates()
                .shape[0]
            ),
            "availability_date_bound": True,
            "historical_vintage_certified": False,
            "point_in_time_backtest_eligible": False,
            "decision_score_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        payload = {
            **self.payload_without_id(),
            "rows": _records(self.frame),
            "raw_periods": self.raw_periods,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _snapshot_directory(path: Path) -> Path:
    if path.is_dir() and (path / "manifest.json").is_file():
        return path.resolve()
    if path.is_file():
        pointer = _read_json(path)
        for key in ("research_directory", "artifact_directory", "snapshot_directory"):
            raw = str(pointer.get(key, "")).strip()
            if raw:
                directory = Path(raw)
                if not directory.is_absolute():
                    directory = Path.cwd() / directory
                if directory.is_dir() and (directory / "manifest.json").is_file():
                    return directory.resolve()
    raise ValueError(f"Research snapshot is unavailable: {path}")


def _default_research_snapshot(live_root: Path) -> Path:
    latest = _read_json(live_root / "latest_run.json")
    raw = str(latest.get("research_directory", "")).strip()
    if latest.get("status") != "completed" or not raw:
        raise ValueError("latest live run has no completed research directory")
    return Path(raw)


def _corp_records(raw_opendart: Mapping[str, object]) -> dict[str, CorpCode]:
    result: dict[str, CorpCode] = {}
    for raw_ticker, raw_company in raw_opendart.items():
        if str(raw_ticker).startswith("_"):
            continue
        if not isinstance(raw_company, dict) or not isinstance(raw_company.get("corp"), dict):
            raise ValueError(f"Research raw OpenDART corp metadata is missing: {raw_ticker}")
        corp = cast(Mapping[str, object], raw_company["corp"])
        ticker = str(corp.get("stock_code", raw_ticker)).strip().zfill(6)
        corp_code = str(corp.get("corp_code", "")).strip()
        corp_name = str(corp.get("corp_name", "")).strip()
        modify_date = str(corp.get("modify_date", "")).strip()
        if (
            len(ticker) != 6
            or not ticker.isdigit()
            or len(corp_code) != 8
            or not corp_code.isdigit()
            or not corp_name
        ):
            raise ValueError(f"Research corp metadata is invalid: {ticker}")
        result[ticker] = CorpCode(
            corp_code=corp_code,
            corp_name=corp_name,
            stock_code=ticker,
            modify_date=date.fromisoformat(modify_date),
        )
    if not result:
        raise ValueError("Research snapshot contains no company metadata")
    return result


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        row: dict[str, object] = {}
        for key, value in raw.items():
            if value is None or value is pd.NA or pd.isna(value):
                row[str(key)] = None
            elif isinstance(value, (date, datetime, pd.Timestamp)):
                row[str(key)] = value.isoformat()
            elif hasattr(value, "item"):
                row[str(key)] = value.item()
            else:
                row[str(key)] = value
        rows.append(row)
    return rows


def collect_stock_totals_history(
    research_snapshot: Path,
    client: StockTotalsHistoryClient,
    *,
    history_years: int,
    now: datetime | None = None,
) -> StockTotalsHistorySnapshot:
    if history_years <= 0 or history_years > 10:
        raise ValueError("history_years must be between 1 and 10")
    directory = _snapshot_directory(research_snapshot)
    manifest = _read_json(directory / "manifest.json")
    research_id = str(manifest.get("snapshot_id", "")).strip()
    if len(research_id) != 64 or any(char not in "0123456789abcdef" for char in research_id):
        raise ValueError("research snapshot_id must be a lowercase SHA-256 digest")
    evaluation_date = date.fromisoformat(str(manifest.get("evaluation_date", "")))
    raw_opendart = _read_json(directory / "raw_opendart.json")
    corps = _corp_records(raw_opendart)

    frames: list[pd.DataFrame] = []
    raw_periods: dict[str, object] = {}
    for ticker in sorted(corps):
        corp = corps[ticker]
        company_raw: list[dict[str, object]] = []
        for business_year, report_code in reversed(
            _candidate_periods(evaluation_date, history_years)
        ):
            batch = client.stock_totals(
                corp,
                business_year=business_year,
                report_code=report_code,
            )
            company_raw.append(
                {
                    "business_year": business_year,
                    "report_code": report_code,
                    "payload": batch.raw_payload,
                    "warnings": list(batch.warnings),
                }
            )
            if batch.frame.empty:
                continue
            visible = batch.frame.loc[
                (pd.to_datetime(batch.frame["period_end"]).dt.date <= evaluation_date)
                & (pd.to_datetime(batch.frame["available_date"]).dt.date <= evaluation_date)
            ].copy()
            if not visible.empty:
                frames.append(visible)
        raw_periods[ticker] = company_raw

    if not frames:
        raise ValueError("No OpenDART stock-total history was available by evaluation date")
    frame = pd.concat(frames, ignore_index=True, sort=False)
    duplicate_keys = [
        "ticker",
        "business_year",
        "report_code",
        "security_class",
        "security_name",
    ]
    if frame.duplicated(duplicate_keys).any():
        raise ValueError("OpenDART stock-total history contains duplicate period/security rows")
    frame = frame.sort_values(
        ["ticker", "available_date", "period_end", "security_class", "security_name"],
        kind="stable",
    ).reset_index(drop=True)
    return StockTotalsHistorySnapshot(
        captured_at=now or datetime.now(UTC),
        evaluation_date=evaluation_date,
        research_snapshot_id=research_id,
        history_years=history_years,
        frame=frame,
        raw_periods=raw_periods,
    )


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_stock_totals_history(
    output_root: Path,
    snapshot: StockTotalsHistorySnapshot,
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    captured = snapshot.captured_at.astimezone(UTC)
    artifact_id = snapshot.snapshot_id
    directory = output_root / (
        captured.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    temporary = output_root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise FileExistsError(f"OpenDART stock-total history artifact already exists: {directory}")
    temporary.mkdir()
    try:
        snapshot.frame.to_csv(temporary / "stock_totals_history.csv", index=False)
        _write_json(temporary / "raw_periods.json", snapshot.raw_periods)
        manifest = {
            **snapshot.payload_without_id(),
            "artifact_id": artifact_id,
            "files": ["stock_totals_history.csv", "raw_periods.json"],
        }
        _write_json(temporary / "manifest.json", manifest)
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "status": "stock_totals_history_captured",
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "stock_totals_history_path": str(
            (directory / "stock_totals_history.csv").resolve()
        ),
        "raw_periods_path": str((directory / "raw_periods.json").resolve()),
        "evaluation_date": snapshot.evaluation_date.isoformat(),
        "research_snapshot_id": snapshot.research_snapshot_id,
        "history_years": snapshot.history_years,
        "row_count": len(snapshot.frame),
        "availability_date_bound": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    _write_json(output_root / LATEST_POINTER_NAME, pointer)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-opendart-stock-totals-history",
        description="Capture period-specific OpenDART share-count history for valuation use",
    )
    parser.add_argument("--research-snapshot", type=Path)
    parser.add_argument("--live-root", type=Path, default=DEFAULT_LIVE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--history-years", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        research = args.research_snapshot or _default_research_snapshot(args.live_root)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")
        client = OpenDartValuationClient(
            OpenDartCredentials.from_env(),
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
        )
        snapshot = collect_stock_totals_history(
            research,
            client,
            history_years=args.history_years,
        )
        pointer = write_stock_totals_history(args.output, snapshot)
        print(json.dumps(pointer, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
