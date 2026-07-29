"""Forward performance labels for previously generated decision records."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd

DEFAULT_HORIZONS = (1, 5, 20, 60)


def _snapshot_directory(path: str | Path) -> Path:
    result = Path(path)
    if not result.is_dir() or not (result / "manifest.json").is_file():
        raise ValueError(f"Valid snapshot directory required: {result}")
    return result


def label_decision_outcomes(
    decision_records: pd.DataFrame,
    future_candles: pd.DataFrame,
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    benchmark: str | None = None,
) -> pd.DataFrame:
    """Label forward returns, upside, and drawdown on trading-day horizons."""

    required_records = {"ticker", "evaluation_date", "reference_price"}
    missing_records = sorted(required_records - set(decision_records.columns))
    if missing_records:
        raise ValueError(f"Missing decision record columns: {', '.join(missing_records)}")
    required_candles = {"symbol", "timestamp", "high", "low", "close"}
    missing_candles = sorted(required_candles - set(future_candles.columns))
    if missing_candles:
        raise ValueError(f"Missing candle columns: {', '.join(missing_candles)}")
    horizon_values = tuple(sorted(set(int(value) for value in horizons)))
    if not horizon_values or any(value <= 0 for value in horizon_values):
        raise ValueError("Outcome horizons must contain positive integers")

    candles = future_candles.copy()
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], errors="raise", utc=True)
    for column in ("high", "low", "close"):
        candles[column] = pd.to_numeric(candles[column], errors="raise")
    candles["trade_date"] = candles["timestamp"].dt.date
    grouped = {
        str(symbol): group.sort_values("timestamp", kind="stable").reset_index(drop=True)
        for symbol, group in candles.groupby("symbol", sort=True)
    }
    if benchmark is not None and benchmark not in grouped:
        raise ValueError(f"Benchmark {benchmark} is not present in future candles")

    rows: list[dict[str, object]] = []
    for raw in decision_records.to_dict(orient="records"):
        ticker = str(raw.get("ticker", "")).strip()
        evaluation_date = date.fromisoformat(str(raw.get("evaluation_date", "")))
        reference_price = float(raw.get("reference_price", 0.0))
        if reference_price <= 0 or not math.isfinite(reference_price):
            raise ValueError(f"Invalid reference_price for {ticker}")
        history = grouped.get(ticker)
        if history is None:
            raise ValueError(f"Future candles do not contain {ticker}")
        candidates = history.index[history["trade_date"] >= evaluation_date].tolist()
        if not candidates:
            start_index = len(history)
        else:
            start_index = int(candidates[0])
            if history.loc[start_index, "trade_date"] == evaluation_date:
                start_index += 1
        for horizon in horizon_values:
            end_index = start_index + horizon - 1
            resolved = start_index < len(history) and end_index < len(history)
            forward_return: float | None = None
            max_upside: float | None = None
            max_drawdown: float | None = None
            excess_return: float | None = None
            end_date: date | None = None
            if resolved:
                window = history.iloc[start_index : end_index + 1]
                end_price = float(window["close"].iloc[-1])
                forward_return = end_price / reference_price - 1.0
                max_upside = float(window["high"].max()) / reference_price - 1.0
                max_drawdown = float(window["low"].min()) / reference_price - 1.0
                end_date = window["trade_date"].iloc[-1]
                if benchmark is not None:
                    benchmark_history = grouped[benchmark]
                    benchmark_candidates = benchmark_history.index[
                        benchmark_history["trade_date"] >= evaluation_date
                    ].tolist()
                    benchmark_start = (
                        int(benchmark_candidates[0]) if benchmark_candidates else len(benchmark_history)
                    )
                    if (
                        benchmark_start < len(benchmark_history)
                        and benchmark_history.loc[benchmark_start, "trade_date"] == evaluation_date
                    ):
                        benchmark_start += 1
                    benchmark_end = benchmark_start + horizon - 1
                    if benchmark_end < len(benchmark_history):
                        benchmark_reference_candidates = benchmark_history.loc[
                            benchmark_history["trade_date"] <= evaluation_date, "close"
                        ]
                        if not benchmark_reference_candidates.empty:
                            benchmark_reference = float(benchmark_reference_candidates.iloc[-1])
                            benchmark_forward = (
                                float(benchmark_history.loc[benchmark_end, "close"])
                                / benchmark_reference
                                - 1.0
                            )
                            excess_return = forward_return - benchmark_forward
            rows.append(
                {
                    "ticker": ticker,
                    "evaluation_date": evaluation_date,
                    "horizon_trading_days": horizon,
                    "resolved": resolved,
                    "end_date": end_date,
                    "reference_price": reference_price,
                    "forward_return": forward_return,
                    "max_upside": max_upside,
                    "max_drawdown": max_drawdown,
                    "benchmark": benchmark,
                    "excess_return": excess_return,
                    "decision_state": raw.get("decision_state"),
                    "action_bias": raw.get("action_bias"),
                    "composite_score": raw.get("composite_score"),
                    "score_coverage": raw.get("score_coverage"),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["ticker", "evaluation_date", "horizon_trading_days"], kind="stable"
    ).reset_index(drop=True)


def write_outcome_labels(
    output_root: str | Path,
    decision_snapshot: str | Path,
    future_market_snapshot: str | Path,
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    benchmark: str | None = None,
) -> tuple[Path, ...]:
    """Write deterministic outcome labels tied to source snapshot IDs."""

    decision_dir = _snapshot_directory(decision_snapshot)
    market_dir = _snapshot_directory(future_market_snapshot)
    decision_manifest = json.loads((decision_dir / "manifest.json").read_text(encoding="utf-8"))
    market_manifest = json.loads((market_dir / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(decision_manifest, dict) or not isinstance(market_manifest, dict):
        raise ValueError("Snapshot manifests must be objects")
    records = pd.read_csv(decision_dir / "decision_records.csv")
    candles = pd.read_csv(market_dir / "candles.csv")
    labels = label_decision_outcomes(
        records,
        candles,
        horizons=horizons,
        benchmark=benchmark,
    )
    decision_id = str(decision_manifest.get("snapshot_id", ""))
    market_id = str(market_manifest.get("snapshot_id", ""))
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / f"{decision_id[:12]}__{market_id[:12]}"
    names = ("manifest.json", "outcome_labels.csv")
    if directory.exists():
        return tuple(directory / name for name in names)
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        labels.to_csv(temporary / "outcome_labels.csv", index=False)
        manifest = {
            "schema_version": 1,
            "decision_snapshot_id": decision_id,
            "future_market_snapshot_id": market_id,
            "benchmark": benchmark,
            "horizons": sorted(set(int(value) for value in horizons)),
            "rows": len(labels),
            "resolved_rows": int(labels["resolved"].sum()) if not labels.empty else 0,
            "order_api_enabled": False,
            "files": ["outcome_labels.csv"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return tuple(directory / name for name in names)
