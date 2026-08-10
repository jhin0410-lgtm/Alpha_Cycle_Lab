"""Inspect freshness and blocker diagnostics for historical P/B evidence.

This command does not rebuild valuation evidence. It reads the immutable historical
P/B artifact, surfaces whether each ticker has an observation on the evaluation
date, and preserves the builder's skipped-date warnings so stale series are not
mistaken for current valuation evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_POINTER = Path(
    "data/private/live-research/historical-pb-evidence/"
    "latest_historical_pb_evidence.json"
)


def _read_json(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _artifact_path(
    pointer: dict[str, object],
    key: str,
    *,
    artifact_directory: Path,
) -> Path:
    raw = str(pointer.get(key, "")).strip()
    if not raw:
        raise ValueError(f"historical P/B pointer is missing {key}")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve(strict=True)
    if resolved.parent != artifact_directory:
        raise ValueError(f"historical P/B {key} crosses artifact boundaries")
    return resolved


def _strict_false(mapping: dict[str, object], key: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"historical P/B must keep {key}=false")


def _ticker(value: object) -> str:
    text = str(value).strip().zfill(6)
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"invalid historical P/B ticker: {value}")
    return text


def _date(value: object, field: str) -> date:
    text = str(value).strip()
    if not text:
        raise ValueError(f"historical P/B summary is missing {field}")
    return date.fromisoformat(text)


def _number(value: object, field: str) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        raise ValueError(f"historical P/B summary has invalid {field}")
    return float(converted)


def inspect_historical_pb_readiness(pointer_path: Path) -> dict[str, object]:
    pointer = _read_json(pointer_path)
    if pointer.get("status") != "historical_pb_observational_evidence_built":
        raise ValueError("historical P/B pointer is not completed")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(pointer, key)

    raw_directory = str(pointer.get("artifact_directory", "")).strip()
    if not raw_directory:
        raise ValueError("historical P/B pointer is missing artifact_directory")
    artifact_directory = Path(raw_directory)
    if not artifact_directory.is_absolute():
        artifact_directory = Path.cwd() / artifact_directory
    artifact_directory = artifact_directory.resolve(strict=True)

    manifest_path = _artifact_path(
        pointer,
        "manifest_path",
        artifact_directory=artifact_directory,
    )
    summary_path = _artifact_path(
        pointer,
        "summary_path",
        artifact_directory=artifact_directory,
    )
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "historical_pb_observational_evidence_built":
        raise ValueError("historical P/B manifest is not completed")
    if manifest.get("artifact_id") != pointer.get("artifact_id"):
        raise ValueError("historical P/B pointer/manifest artifact mismatch")
    evaluation_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if str(manifest.get("evaluation_date", "")) != evaluation_date.isoformat():
        raise ValueError("historical P/B pointer/manifest evaluation date mismatch")

    warnings_raw = manifest.get("warnings", [])
    if not isinstance(warnings_raw, list):
        raise ValueError("historical P/B manifest warnings must be a list")
    warnings = [str(value) for value in warnings_raw]

    summary = pd.read_csv(summary_path, dtype={"ticker": "string"})
    required = {
        "ticker",
        "observation_count",
        "first_date",
        "last_date",
        "latest_pb",
        "pb_min",
        "pb_p25",
        "pb_median",
        "pb_p75",
        "pb_max",
        "latest_pb_percentile",
        "band_status",
    }
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"historical P/B summary missing columns: {sorted(missing)}")
    if summary.empty:
        raise ValueError("historical P/B summary is empty")

    symbols: list[dict[str, object]] = []
    for raw in summary.to_dict(orient="records"):
        ticker = _ticker(raw["ticker"])
        first_date = _date(raw["first_date"], "first_date")
        last_date = _date(raw["last_date"], "last_date")
        if last_date > evaluation_date:
            raise ValueError("historical P/B summary contains a future observation")
        observation_count = int(_number(raw["observation_count"], "observation_count"))
        band_status = str(raw["band_status"]).strip()
        if band_status not in {
            "insufficient_history",
            "observational_1y_ready",
            "observational_2y_ready",
        }:
            raise ValueError(f"unexpected historical P/B band_status: {band_status}")
        current_observation = last_date == evaluation_date
        band_history_ready = band_status != "insufficient_history"
        ticker_warnings = [
            warning for warning in warnings if warning.startswith(f"{ticker}:")
        ]
        symbols.append(
            {
                "ticker": ticker,
                "observation_count": observation_count,
                "first_date": first_date.isoformat(),
                "last_date": last_date.isoformat(),
                "latest_observation_lag_days": (evaluation_date - last_date).days,
                "current_observation_available": current_observation,
                "current_observation_status": (
                    "current_on_evaluation_date"
                    if current_observation
                    else "stale_before_evaluation_date"
                ),
                "historical_band_status": band_status,
                "historical_band_history_ready": band_history_ready,
                "current_observational_band_usable": (
                    current_observation and band_history_ready
                ),
                "latest_pb": _number(raw["latest_pb"], "latest_pb"),
                "pb_min": _number(raw["pb_min"], "pb_min"),
                "pb_p25": _number(raw["pb_p25"], "pb_p25"),
                "pb_median": _number(raw["pb_median"], "pb_median"),
                "pb_p75": _number(raw["pb_p75"], "pb_p75"),
                "pb_max": _number(raw["pb_max"], "pb_max"),
                "latest_pb_percentile": _number(
                    raw["latest_pb_percentile"],
                    "latest_pb_percentile",
                ),
                "builder_warnings": ticker_warnings,
            }
        )

    return {
        "status": "historical_pb_readiness_inspected",
        "evaluation_date": evaluation_date.isoformat(),
        "artifact_id": str(pointer.get("artifact_id", "")),
        "all_symbols_current_on_evaluation_date": all(
            bool(item["current_observation_available"]) for item in symbols
        ),
        "all_symbols_current_observational_band_usable": all(
            bool(item["current_observational_band_usable"]) for item in symbols
        ),
        "symbols": symbols,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-historical-pb-readiness",
        description=(
            "Inspect historical P/B freshness, band readiness, and skipped-date blockers"
        ),
    )
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = inspect_historical_pb_readiness(args.pointer)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
