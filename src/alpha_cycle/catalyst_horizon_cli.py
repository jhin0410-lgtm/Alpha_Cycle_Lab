"""Capture source-bounded future catalyst event packs into local research artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.catalyst_horizon import build_catalyst_horizon_evidence

DEFAULT_OUTPUT = Path("data/private/live-research/catalyst-horizon-evidence")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _load_events(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Catalyst horizon input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Catalyst horizon input is invalid JSON: {path}") from exc
    raw_events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("Catalyst horizon input must contain a non-empty events array")
    result: list[dict[str, object]] = []
    for value in raw_events:
        if not isinstance(value, dict):
            raise ValueError("Catalyst horizon event must be an object")
        result.append({str(key): item for key, item in cast(dict[object, object], value).items()})
    return result


def _event_payload(event: object) -> dict[str, object]:
    row = event
    return {
        "event_id": row.event_id,
        "ticker": row.ticker,
        "sector_id": row.sector_id,
        "title": row.title,
        "description": row.description,
        "source_role": row.source_role,
        "source_url": row.source_url,
        "source_published_date": row.source_published_date.isoformat(),
        "evaluation_date": row.evaluation_date.isoformat(),
        "event_date": row.event_date.isoformat() if row.event_date else None,
        "window_start": row.window_start.isoformat() if row.window_start else None,
        "window_end": row.window_end.isoformat() if row.window_end else None,
        "timing_status": row.timing_status,
        "horizon_days": row.horizon_days,
        "horizon_bucket": row.horizon_bucket,
        "prerequisite_status": row.prerequisite_status,
        "prerequisite": row.prerequisite,
        "market_pricing_status": row.market_pricing_status,
        "surprise_potential": row.surprise_potential,
        "binary_event": row.binary_event,
        "thesis_invalidation_if_failed": row.thesis_invalidation_if_failed,
        "decision_score_enabled": False,
    }


def write_catalyst_horizon_evidence(
    raw_events: list[dict[str, object]],
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence = build_catalyst_horizon_evidence(raw_events, evaluation_date=evaluation_date)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Catalyst horizon artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        events_payload = [_event_payload(event) for event in evidence.events]
        (temporary / "events.json").write_text(
            json.dumps(events_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "status": "catalyst_horizon_evidence_captured",
            "evidence_id": evidence.evidence_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "event_count": len(evidence.events),
            "tickers": sorted({event.ticker for event in evidence.events}),
            "horizon_buckets": sorted({event.horizon_bucket for event in evidence.events}),
            "input_path": str(Path(input_path).resolve()) if input_path else None,
            "source_bytes_archived": False,
            "historical_snapshot_certified": False,
            "decision_score_enabled": False,
            "forecast_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": ["events.json"],
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
        "status": "catalyst_horizon_evidence_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "events_path": str((directory / "events.json").resolve()),
        "source_bytes_archived": False,
        "historical_snapshot_certified": False,
        "decision_score_enabled": False,
        "forecast_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_catalyst_horizon_evidence.json"
    temporary_pointer = root / ".latest_catalyst_horizon_evidence.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-catalyst-horizon",
        description="Validate and capture future catalyst event packs; no score or forecast is produced",
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = write_catalyst_horizon_evidence(
            _load_events(args.input),
            evaluation_date=args.evaluation_date,
            output=args.output,
            input_path=args.input,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
