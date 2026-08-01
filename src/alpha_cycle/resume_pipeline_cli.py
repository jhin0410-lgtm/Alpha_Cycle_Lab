"""Resume valuation and decision stages from fresh linked source snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence import (
    DecisionPolicy,
    build_investment_decision_snapshot,
    build_valuation_evidence_snapshot,
    load_company_exposures,
    write_investment_decision_snapshot,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.live_pipeline_cli import (
    DEFAULT_MARKET_SYMBOLS,
    DEFAULT_OUTPUT_ROOT,
    PipelineStageError,
    _default_security_mappings,
    _run_stage,
    _write_status,
)
from alpha_cycle.providers import OpenDartCredentials, OpenDartValuationClient

KOREA_TZ = ZoneInfo("Asia/Seoul")
KRX_SESSION_CLOSE = time(15, 30)
DEFAULT_MAX_MARKET_AGE_HOURS = 72.0
MAX_MARKET_AGE_HOURS = 168.0
_REQUIRED_MARKET_FILES = (
    "manifest.json",
    "prices.csv",
    "candles.csv",
    "technical_features.csv",
)
_REQUIRED_RESEARCH_FILES = (
    "manifest.json",
    "financials.csv",
    "disclosures.csv",
    "macro.csv",
    "raw_opendart.json",
)


@dataclass(frozen=True)
class ResumePair:
    market_directory: Path
    research_directory: Path
    market_manifest: Mapping[str, object]
    research_manifest: Mapping[str, object]
    source_evaluation_date: date
    age: timedelta


def _read_manifest(directory: Path) -> Mapping[str, object]:
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot manifest must be an object: {directory}")
    return cast(Mapping[str, object], payload)


def _has_files(directory: Path, names: tuple[str, ...]) -> bool:
    return directory.is_dir() and all((directory / name).is_file() for name in names)


def _aware_datetime(value: object, field: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _find_market_directory(
    root: Path,
    snapshot_id: str,
) -> tuple[Path, Mapping[str, object]] | None:
    market_root = root / "market-intelligence"
    if not market_root.is_dir():
        return None
    for directory in sorted(market_root.iterdir(), reverse=True):
        if not _has_files(directory, _REQUIRED_MARKET_FILES):
            continue
        try:
            manifest = _read_manifest(directory)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        if str(manifest.get("snapshot_id", "")) == snapshot_id:
            return directory, manifest
    return None


def _potential_completed_session_after(captured_at: datetime, now: datetime) -> bool:
    """Conservatively reject snapshots crossed by a possible completed KRX session."""

    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Resume clock must be timezone-aware")

    captured_local = captured_at.astimezone(KOREA_TZ)
    now_local = now.astimezone(KOREA_TZ)
    if captured_local > now_local:
        return True

    current_date = captured_local.date()
    while current_date <= now_local.date():
        if current_date.weekday() < 5:
            possible_close = datetime.combine(
                current_date,
                KRX_SESSION_CLOSE,
                tzinfo=KOREA_TZ,
            )
            if captured_local < possible_close <= now_local:
                return True
        current_date += timedelta(days=1)
    return False


def find_resume_pair(
    output_root: Path,
    *,
    evaluation_date: date,
    now: datetime,
    max_age_hours: float,
) -> ResumePair | None:
    """Find the newest linked, fresh pair without an intervening completed session."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Resume clock must be timezone-aware")
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    research_root = output_root / "research-intelligence"
    if not research_root.is_dir():
        return None

    required_symbols = set(DEFAULT_MARKET_SYMBOLS)
    max_age = timedelta(hours=max_age_hours)
    for research_directory in sorted(research_root.iterdir(), reverse=True):
        if not _has_files(research_directory, _REQUIRED_RESEARCH_FILES):
            continue
        try:
            research_manifest = _read_manifest(research_directory)
            source_evaluation_date = date.fromisoformat(
                str(research_manifest.get("evaluation_date", ""))
            )
            if source_evaluation_date > evaluation_date:
                continue
        except (ValueError, OSError, json.JSONDecodeError):
            continue

        market_snapshot_id = str(research_manifest.get("market_snapshot_id", ""))
        if not market_snapshot_id:
            continue
        found = _find_market_directory(output_root, market_snapshot_id)
        if found is None:
            continue
        market_directory, market_manifest = found

        try:
            captured_at = _aware_datetime(
                market_manifest.get("captured_at"),
                "captured_at",
            )
        except ValueError:
            continue
        age = now.astimezone(UTC) - captured_at.astimezone(UTC)
        if age < timedelta(0) or age > max_age:
            continue
        if captured_at.astimezone(KOREA_TZ).date() > evaluation_date:
            continue
        if _potential_completed_session_after(captured_at, now):
            continue

        symbols_value = market_manifest.get("symbols", [])
        if not isinstance(symbols_value, list):
            continue
        if not required_symbols.issubset({str(item) for item in symbols_value}):
            continue
        if str(market_manifest.get("interval", "")) != "1d":
            continue
        if bool(market_manifest.get("adjusted", True)):
            continue

        return ResumePair(
            market_directory=market_directory,
            research_directory=research_directory,
            market_manifest=market_manifest,
            research_manifest=research_manifest,
            source_evaluation_date=source_evaluation_date,
            age=age,
        )
    return None


def _execute(args: argparse.Namespace) -> dict[str, object]:
    now = datetime.now(KOREA_TZ)
    requested_evaluation_date: date = args.evaluation_date or now.date()
    pair = find_resume_pair(
        args.output,
        evaluation_date=requested_evaluation_date,
        now=now,
        max_age_hours=args.max_market_age_hours,
    )
    if pair is None:
        raise PipelineStageError(
            "resume_validation",
            ValueError(
                "No linked market/research snapshot pair is fresh enough and free of "
                "an intervening completed weekday session within "
                f"{args.max_market_age_hours:g} hours"
            ),
        )

    valuation_client = OpenDartValuationClient(
        OpenDartCredentials.from_env(),
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
    )
    valuation_snapshot = _run_stage(
        "valuation",
        lambda: build_valuation_evidence_snapshot(
            pair.research_directory,
            pair.market_directory,
            valuation_client,
            history_years=args.history_years,
            fs_div="CFS",
            security_mappings=_default_security_mappings(),
        ),
    )
    valuation_files = _run_stage(
        "valuation_write",
        lambda: write_valuation_evidence_snapshot(
            args.output / "valuation-intelligence",
            valuation_snapshot,
        ),
    )
    valuation_directory = valuation_files[0].parent

    company_config = Path("config/company_exposures.local.yaml")
    exposures = load_company_exposures(
        company_config if company_config.is_file() else None
    )
    decision_snapshot = _run_stage(
        "decision",
        lambda: build_investment_decision_snapshot(
            pair.research_directory,
            pair.market_directory,
            valuation_snapshot=valuation_directory,
            exposures=exposures,
            policy=DecisionPolicy(),
        ),
    )
    decision_files = _run_stage(
        "decision_write",
        lambda: write_investment_decision_snapshot(
            args.output / "decision-intelligence",
            decision_snapshot,
        ),
    )
    decision_directory = decision_files[0].parent
    valuation_frame = valuation_snapshot.valuation_metrics
    scorecards = decision_snapshot.scorecards
    captured_at = _aware_datetime(
        pair.market_manifest.get("captured_at"),
        "captured_at",
    )
    captured_date = captured_at.astimezone(KOREA_TZ).date()
    cross_date_resume = captured_date != requested_evaluation_date
    warnings = [
        "market_snapshot_resumed_after_live_provider_block",
        f"resumed_market_age_minutes={pair.age.total_seconds() / 60.0:.1f}",
    ]
    if cross_date_resume:
        warnings.append(
            "cross_date_snapshot_resume="
            f"{captured_date.isoformat()}->{requested_evaluation_date.isoformat()}"
        )
    warnings.extend(decision_snapshot.warnings)

    return {
        "status": "completed",
        "execution_mode": "resumed_linked_snapshots",
        "evaluation_date": pair.source_evaluation_date.isoformat(),
        "requested_evaluation_date": requested_evaluation_date.isoformat(),
        "market_capture_date": captured_date.isoformat(),
        "cross_date_resume": cross_date_resume,
        "market_source": "resumed_snapshot",
        "research_source": "resumed_snapshot",
        "market_snapshot_age_minutes": round(pair.age.total_seconds() / 60.0, 1),
        "market_snapshot_id": str(pair.market_manifest.get("snapshot_id", "")),
        "research_snapshot_id": str(pair.research_manifest.get("snapshot_id", "")),
        "valuation_snapshot_id": valuation_snapshot.snapshot_id,
        "decision_snapshot_id": decision_snapshot.snapshot_id,
        "market_directory": str(pair.market_directory.resolve()),
        "research_directory": str(pair.research_directory.resolve()),
        "valuation_directory": str(valuation_directory.resolve()),
        "decision_directory": str(decision_directory.resolve()),
        "report_path": str((decision_directory / "report.md").resolve()),
        "market_cap_complete_count": int(
            valuation_frame["market_cap_complete"].astype(bool).sum()
        ),
        "valuation_scored_count": int(
            valuation_frame["valuation_score"].notna().sum()
        ),
        "decision_states": {
            str(key): int(value)
            for key, value in scorecards["decision_state"].value_counts().items()
        },
        "warnings": warnings,
        "order_api_enabled": False,
    }


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-resume",
        description=(
            "Resume valuation and decision from fresh linked source snapshots when no "
            "possible completed weekday market session occurred after capture"
        ),
    )
    parser.add_argument("--evaluation-date", type=_date_argument)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--history-years", type=int, default=3)
    parser.add_argument(
        "--max-market-age-hours",
        type=float,
        default=DEFAULT_MAX_MARKET_AGE_HOURS,
    )
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.history_years <= 0 or args.history_years > 10:
        raise ValueError("--history-years must be between 1 and 10")
    if (
        args.max_market_age_hours <= 0
        or args.max_market_age_hours > MAX_MARKET_AGE_HOURS
    ):
        raise ValueError(
            f"--max-market-age-hours must be between 0 and {MAX_MARKET_AGE_HOURS:g}"
        )
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.max_retries < 0:
        raise ValueError("--max-retries cannot be negative")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        _validate_args(args)
        result_payload = _execute(args)
        status_path = _write_status(args.output, result_payload)
        result_payload["status_path"] = str(status_path.resolve())
        print(json.dumps(result_payload, ensure_ascii=False, sort_keys=True))
        return 0
    except PipelineStageError as exc:
        if args is None:
            raise
        reason = (
            "resume_unavailable"
            if exc.stage == "resume_validation"
            else "pipeline_error"
        )
        stage_error_payload: dict[str, object] = {
            "status": "failed",
            "stage": exc.stage,
            "reason": reason,
            "error": str(exc.cause),
            "next_action": (
                "Register the current public IP in TossInvest and rerun the "
                "live pipeline."
                if exc.stage == "resume_validation"
                else "Review the stage error and rerun after correction."
            ),
            "rerun_command": ".\\scripts\\run_live_pipeline.cmd",
            "outputs_available": False,
            "order_api_enabled": False,
        }
        status_path = _write_status(args.output, stage_error_payload)
        stage_error_payload["status_path"] = str(status_path.resolve())
        print(
            json.dumps(stage_error_payload, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 4 if exc.stage == "resume_validation" else 2
    except (ValueError, OSError, TypeError) as exc:
        output = args.output if args is not None else DEFAULT_OUTPUT_ROOT
        validation_error_payload = {
            "status": "failed",
            "stage": "validation",
            "reason": "invalid_configuration",
            "error": str(exc),
            "outputs_available": False,
            "order_api_enabled": False,
        }
        _write_status(output, validation_error_payload)
        print(
            json.dumps(validation_error_payload, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
