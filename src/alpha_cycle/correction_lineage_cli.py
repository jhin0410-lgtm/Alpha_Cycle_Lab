"""Inspect correction-disclosure lineage from the latest live pipeline run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_STATUS_PATH = Path("data/private/live-research/latest_run.json")
DISPLAY_COLUMNS = (
    "ticker",
    "receipt_date",
    "report_name",
    "correction_parent_rcept_no",
    "correction_chain_root_rcept_no",
    "correction_chain_order",
    "correction_lineage_status",
    "is_latest_in_correction_chain",
)
_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "예", "정정"})


def _read_status(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise ValueError(f"Pipeline status file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Pipeline status must be a JSON object: {path}")
    return cast(Mapping[str, object], payload)


def _decision_directory(status: Mapping[str, object], status_path: Path) -> Path:
    raw = status.get("decision_directory")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Pipeline status does not contain decision_directory")
    directory = Path(raw)
    if not directory.is_absolute():
        directory = (status_path.parent / directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"Decision directory does not exist: {directory}")
    return directory


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, float):
        return not pd.isna(value) and value == 1.0
    return str(value).strip().casefold() in _TRUE_VALUES


def _ticker(value: str) -> str:
    text = value.strip()
    if not re.fullmatch(r"\d{1,6}", text):
        raise argparse.ArgumentTypeError("ticker must contain one to six digits")
    return text.zfill(6)


def load_correction_lineage(
    status_path: str | Path = DEFAULT_STATUS_PATH,
    *,
    ticker: str | None = None,
    only_latest: bool = False,
) -> tuple[pd.DataFrame, Path]:
    """Load normalized correction rows and return their source CSV path."""

    path = Path(status_path)
    status = _read_status(path)
    if status.get("status") != "completed":
        raise ValueError(
            "Latest pipeline status is not completed: "
            f"{status.get('status', 'missing')}"
        )
    events_path = _decision_directory(status, path) / "disclosure_events.csv"
    if not events_path.is_file():
        raise ValueError(f"Disclosure event file does not exist: {events_path}")

    events = pd.read_csv(
        events_path,
        dtype={"ticker": "string", "rcept_no": "string"},
    )
    required = {"ticker", "receipt_date", "report_name", "is_correction"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(
            "Disclosure event file is missing required columns: " + ", ".join(missing)
        )
    lineage_missing = sorted(set(DISPLAY_COLUMNS) - set(events.columns))
    if lineage_missing:
        raise ValueError(
            "Correction-lineage columns are unavailable; update main and rerun the live "
            "pipeline. Missing: " + ", ".join(lineage_missing)
        )

    events["ticker"] = events["ticker"].astype("string").str.strip().str.zfill(6)
    correction_mask = events["is_correction"].map(_as_bool)
    result = events.loc[correction_mask].copy()
    if ticker is not None:
        normalized_ticker = _ticker(ticker)
        result = result.loc[result["ticker"] == normalized_ticker].copy()
    if only_latest:
        latest_mask = result["is_latest_in_correction_chain"].map(_as_bool)
        result = result.loc[latest_mask].copy()

    result["receipt_date"] = pd.to_datetime(
        result["receipt_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    result["correction_chain_order"] = pd.to_numeric(
        result["correction_chain_order"], errors="raise"
    ).astype("Int64")
    result = result.sort_values(
        ["ticker", "receipt_date", "correction_chain_order", "rcept_no"],
        kind="stable",
    )
    return result.loc[:, list(DISPLAY_COLUMNS)].reset_index(drop=True), events_path


def _render(frame: pd.DataFrame, output_format: str) -> str:
    if output_format == "json":
        return frame.to_json(orient="records", force_ascii=False, indent=2)
    if output_format == "csv":
        return frame.to_csv(index=False)
    return frame.to_string(index=False, na_rep="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-correction-lineage",
        description="Show correction-disclosure provenance from the latest live run",
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=DEFAULT_STATUS_PATH,
        help="path to latest_run.json",
    )
    parser.add_argument("--ticker", type=_ticker)
    parser.add_argument(
        "--only-latest",
        action="store_true",
        help="show only the newest event in each correction chain",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        frame, source = load_correction_lineage(
            args.status,
            ticker=args.ticker,
            only_latest=args.only_latest,
        )
        print(f"Source: {source}")
        print(f"Correction disclosures: {len(frame)}")
        if frame.empty:
            print("No correction disclosures found.")
        else:
            print(_render(frame, args.format))
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"correction-lineage error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
