"""Capture official-system U.S. macro/liquidity series into local research artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from alpha_cycle.intelligence.macro_liquidity_evidence import (
    MacroLiquidityEvidence,
    build_macro_liquidity_evidence,
    load_macro_liquidity_registry,
)

DEFAULT_REGISTRY = Path("config/macro_liquidity_sources.yaml")
DEFAULT_OUTPUT = Path("data/private/live-research/macro-liquidity-evidence")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _download(url: str, *, timeout_seconds: float = 15.0) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "Alpha-Cycle-Lab/0.1 macro-liquidity-readonly"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        content = response.read()
    if not content:
        raise ValueError(f"Macro liquidity source returned no bytes: {url}")
    return content


def write_macro_liquidity_evidence(
    evidence: MacroLiquidityEvidence,
    output: str | Path,
    *,
    registry_path: str | Path,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Macro liquidity artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        evidence.series.to_csv(temporary / "series_summary.csv", index=False)
        evidence.observations.to_csv(temporary / "observations.csv", index=False)
        manifest = {
            "schema_version": 1,
            "status": "macro_liquidity_evidence_captured",
            "evidence_id": evidence.evidence_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evidence.evaluation_date.isoformat(),
            "series_ids": evidence.series["series_id"].astype(str).tolist(),
            "series_count": int(len(evidence.series)),
            "observation_count": int(len(evidence.observations)),
            "registry_path": str(Path(registry_path).resolve()),
            "current_endpoint_snapshot": True,
            "historical_vintage_certified": False,
            "point_in_time_backtest_eligible": False,
            "decision_score_enabled": False,
            "composite_liquidity_score_enabled": False,
            "forecast_enabled": False,
            "causal_claim_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": ["series_summary.csv", "observations.csv"],
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

    pointer = {
        "schema_version": 1,
        "status": "macro_liquidity_evidence_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "series_summary_path": str((directory / "series_summary.csv").resolve()),
        "observations_path": str((directory / "observations.csv").resolve()),
        "current_endpoint_snapshot": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "decision_score_enabled": False,
        "composite_liquidity_score_enabled": False,
        "forecast_enabled": False,
        "causal_claim_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_macro_liquidity_evidence.json"
    temporary_pointer = root / ".latest_macro_liquidity_evidence.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def capture_macro_liquidity(
    *,
    evaluation_date: date,
    registry: str | Path = DEFAULT_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    timeout_seconds: float = 15.0,
) -> dict[str, object]:
    specs = load_macro_liquidity_registry(registry)
    evidence = build_macro_liquidity_evidence(
        specs,
        lambda url: _download(url, timeout_seconds=timeout_seconds),
        evaluation_date=evaluation_date,
    )
    return write_macro_liquidity_evidence(
        evidence,
        output,
        registry_path=registry,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-macro-liquidity",
        description=(
            "Capture registered Federal Reserve/FRED macro-liquidity evidence read-only; "
            "no composite liquidity score or trading signal is produced"
        ),
    )
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        result = capture_macro_liquidity(
            evaluation_date=args.evaluation_date,
            registry=args.registry,
            output=args.output,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
