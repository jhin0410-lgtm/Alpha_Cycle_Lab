"""Build immutable, non-scoring historical P/B evidence from validated local sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.historical_pb import build_historical_pb_evidence
from alpha_cycle.intelligence.valuation import load_security_mappings

DEFAULT_LIVE_ROOT = Path("data/private/live-research")
DEFAULT_PRICE_POINTER = (
    DEFAULT_LIVE_ROOT
    / "kiwoom-openapi-plus-valuation-history"
    / "latest_valuation_history_export.json"
)
DEFAULT_SHARE_POINTER = (
    DEFAULT_LIVE_ROOT
    / "opendart-stock-totals-history"
    / "latest_opendart_stock_totals_history.json"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_LIVE_ROOT / "historical-pb-evidence"
DEFAULT_SECURITY_CONFIG = Path("config/security_mappings.local.yaml")
LATEST_POINTER_NAME = "latest_historical_pb_evidence.json"
SOURCE_SCOPE = "unadjusted_price_x_observable_shares_x_observable_book_equity"
SCHEMA_VERSION = 1


def _read_json(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], value)


def _sha256(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _strict_false(mapping: dict[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"{label} must keep {key}=false")


def _path_from_pointer(pointer: dict[str, object], key: str, *, label: str) -> Path:
    raw = str(pointer.get(key, "")).strip()
    if not raw:
        raise ValueError(f"{label} pointer is missing {key}")
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=True)


def _load_price_history(pointer_path: Path) -> tuple[str, pd.DataFrame]:
    pointer = _read_json(pointer_path)
    if pointer.get("status") != "completed":
        raise ValueError("Kiwoom valuation-history pointer is not completed")
    if pointer.get("provider") != "kiwoom_openapi_plus":
        raise ValueError("unexpected valuation-history price provider")
    if pointer.get("purpose") != "historical_valuation_price_reconstruction":
        raise ValueError("Kiwoom valuation-history purpose is invalid")
    if pointer.get("adjusted_prices") is not False:
        raise ValueError("historical P/B requires adjusted_prices=false")
    if pointer.get("price_basis") != "unadjusted":
        raise ValueError("historical P/B requires price_basis=unadjusted")
    if str(pointer.get("adjustment_request_value", "")) != "0":
        raise ValueError("historical P/B requires opt10081 adjustment request 0")
    for key in (
        "primary_market_evidence_eligible",
        "technical_indicator_eligible",
        "decision_score_enabled",
        "point_in_time_backtest_eligible",
        "account_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(pointer, key, label="Kiwoom valuation-history pointer")
    snapshot_id = _sha256(pointer.get("snapshot_id"), "Kiwoom valuation-history snapshot_id")
    manifest_path = _path_from_pointer(pointer, "manifest_path", label="Kiwoom valuation-history")
    manifest = _read_json(manifest_path)
    if _sha256(manifest.get("snapshot_id"), "Kiwoom valuation-history manifest snapshot_id") != snapshot_id:
        raise ValueError("Kiwoom valuation-history pointer/manifest snapshot mismatch")
    if manifest.get("source_scope") != "kiwoom_opt10081_unadjusted_historical_valuation_prices":
        raise ValueError("Kiwoom valuation-history source scope is invalid")
    if manifest.get("price_basis") != "unadjusted" or manifest.get("adjusted_prices") is not False:
        raise ValueError("Kiwoom valuation-history manifest is not unadjusted")
    directory = manifest_path.parent
    bars_name = str(manifest.get("daily_bars_file", "")).strip()
    if not bars_name or Path(bars_name).name != bars_name:
        raise ValueError("Kiwoom valuation-history daily bars filename is invalid")
    bars_path = (directory / bars_name).resolve(strict=True)
    bars_path.relative_to(directory.resolve())
    frame = pd.read_csv(bars_path, dtype={"ticker": "string"})
    return snapshot_id, frame


def _load_share_history(pointer_path: Path) -> tuple[str, str, date, pd.DataFrame]:
    pointer = _read_json(pointer_path)
    if pointer.get("status") != "stock_totals_history_captured":
        raise ValueError("OpenDART stock-total history pointer is not completed")
    if pointer.get("availability_date_bound") is not True:
        raise ValueError("OpenDART stock-total history lacks availability-date binding")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "decision_score_enabled",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(pointer, key, label="OpenDART stock-total history pointer")
    artifact_id = _sha256(pointer.get("artifact_id"), "OpenDART stock-total history artifact_id")
    research_id = _sha256(pointer.get("research_snapshot_id"), "stock-total research_snapshot_id")
    evaluation_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    frame_path = _path_from_pointer(pointer, "stock_totals_history_path", label="OpenDART stock-total history")
    manifest_path = _path_from_pointer(pointer, "manifest_path", label="OpenDART stock-total history")
    if frame_path.parent != manifest_path.parent:
        raise ValueError("OpenDART stock-total history files cross artifact boundaries")
    manifest = _read_json(manifest_path)
    if _sha256(manifest.get("artifact_id"), "OpenDART stock-total manifest artifact_id") != artifact_id:
        raise ValueError("OpenDART stock-total pointer/manifest artifact mismatch")
    if _sha256(manifest.get("research_snapshot_id"), "OpenDART stock-total manifest research id") != research_id:
        raise ValueError("OpenDART stock-total research lineage mismatch")
    frame = pd.read_csv(frame_path, dtype={"ticker": "string", "report_code": "string"})
    return artifact_id, research_id, evaluation_date, frame


def _latest_valuation_directory(live_root: Path) -> Path:
    latest = _read_json(live_root / "latest_run.json")
    raw = str(latest.get("valuation_directory", "")).strip()
    if latest.get("status") != "completed" or not raw:
        raise ValueError("latest live run has no completed valuation directory")
    directory = Path(raw)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    return directory.resolve(strict=True)


def _load_financial_history(
    valuation_directory: Path,
) -> tuple[str, str, date, tuple[str, ...], pd.DataFrame]:
    manifest = _read_json(valuation_directory / "manifest.json")
    valuation_id = _sha256(manifest.get("snapshot_id"), "valuation snapshot_id")
    research_id = _sha256(manifest.get("research_snapshot_id"), "valuation research_snapshot_id")
    evaluation_date = date.fromisoformat(str(manifest.get("evaluation_date", "")))
    raw_symbols = manifest.get("symbols", [])
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ValueError("valuation manifest contains no symbols")
    symbols = tuple(sorted(str(value).strip().zfill(6) for value in raw_symbols))
    frame = pd.read_csv(
        valuation_directory / "financial_history.csv",
        dtype={"ticker": "string", "report_code": "string"},
    )
    return valuation_id, research_id, evaluation_date, symbols, frame


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


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def run_historical_pb(
    *,
    price_pointer: Path,
    share_pointer: Path,
    valuation_directory: Path,
    output_root: Path,
    security_config: Path | None,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("historical P/B clock must be timezone-aware")
    price_id, prices = _load_price_history(price_pointer)
    share_id, share_research_id, share_date, shares = _load_share_history(share_pointer)
    valuation_id, valuation_research_id, valuation_date, symbols, financials = (
        _load_financial_history(valuation_directory)
    )
    if share_research_id != valuation_research_id:
        raise ValueError("stock-total history and valuation snapshot use different research evidence")
    if share_date != valuation_date:
        raise ValueError("stock-total history and valuation snapshot use different evaluation dates")
    mappings = load_security_mappings(security_config)
    evidence = build_historical_pb_evidence(
        prices,
        shares,
        financials,
        evaluation_date=valuation_date,
        security_mappings=mappings,
    )
    observed = tuple(sorted(evidence.summary["ticker"].astype(str).tolist()))
    if observed != symbols:
        missing = sorted(set(symbols) - set(observed))
        raise ValueError(
            "historical P/B did not produce every valuation symbol; missing=" + ",".join(missing)
        )

    payload_without_id: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": "historical_pb_observational_evidence_built",
        "source_scope": SOURCE_SCOPE,
        "captured_at": now.astimezone(UTC).isoformat(),
        "evaluation_date": valuation_date.isoformat(),
        "price_history_snapshot_id": price_id,
        "stock_totals_history_artifact_id": share_id,
        "valuation_snapshot_id": valuation_id,
        "research_snapshot_id": valuation_research_id,
        "symbols": list(symbols),
        "summary": _records(evidence.summary),
        "warnings": list(evidence.warnings),
        "price_basis": "unadjusted",
        "share_availability_date_bound": True,
        "equity_availability_date_bound": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    canonical = json.dumps(
        {**payload_without_id, "series": _records(evidence.series)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    artifact_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    captured = now.astimezone(UTC)
    directory = output_root / (
        captured.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    temporary = output_root / f".{directory.name}.tmp"
    output_root.mkdir(parents=True, exist_ok=True)
    if directory.exists() or temporary.exists():
        raise FileExistsError(f"historical P/B artifact already exists: {directory}")
    temporary.mkdir()
    try:
        evidence.series.to_csv(temporary / "historical_pb_series.csv", index=False)
        evidence.summary.to_csv(temporary / "historical_pb_summary.csv", index=False)
        _write_json(
            temporary / "manifest.json",
            {
                **payload_without_id,
                "artifact_id": artifact_id,
                "files": ["historical_pb_series.csv", "historical_pb_summary.csv"],
            },
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "status": "historical_pb_observational_evidence_built",
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "series_path": str((directory / "historical_pb_series.csv").resolve()),
        "summary_path": str((directory / "historical_pb_summary.csv").resolve()),
        "evaluation_date": valuation_date.isoformat(),
        "symbols": list(symbols),
        "price_history_snapshot_id": price_id,
        "stock_totals_history_artifact_id": share_id,
        "valuation_snapshot_id": valuation_id,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
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
        prog="alpha-cycle-historical-pb",
        description="Build non-scoring historical P/B evidence from unadjusted prices and observable OpenDART inputs",
    )
    parser.add_argument("--live-root", type=Path, default=DEFAULT_LIVE_ROOT)
    parser.add_argument("--price-pointer", type=Path, default=DEFAULT_PRICE_POINTER)
    parser.add_argument("--share-pointer", type=Path, default=DEFAULT_SHARE_POINTER)
    parser.add_argument("--valuation-directory", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--security-config", type=Path, default=DEFAULT_SECURITY_CONFIG)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        valuation_directory = args.valuation_directory or _latest_valuation_directory(args.live_root)
        security_config: Path | None = args.security_config
        if security_config is not None and not security_config.is_file():
            raise ValueError(f"Security config does not exist: {security_config}")
        pointer = run_historical_pb(
            price_pointer=args.price_pointer,
            share_pointer=args.share_pointer,
            valuation_directory=valuation_directory,
            output_root=args.output,
            security_config=security_config,
            now=datetime.now(UTC),
        )
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
