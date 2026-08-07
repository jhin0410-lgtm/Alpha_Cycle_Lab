"""Inspect correction-delta certification results from the latest live run."""

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
_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "예", "정정"})
_BASE_COLUMNS = (
    "ticker",
    "receipt_date",
    "report_name",
    "rcept_no",
    "correction_lineage_status",
    "correction_chain_order",
    "lineage_parent_rcept_no",
    "document_evidence_status",
    "body_metrics_status",
    "body_metrics_type",
    "correction_delta_status",
    "verified_field_count",
    "changed_field_count",
    "mismatch_fields",
)


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


def _json_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return cast(Mapping[str, object], parsed) if isinstance(parsed, dict) else None


def _delta_detail(value: object) -> tuple[int | None, int | None, str]:
    payload = _json_mapping(value)
    if payload is None:
        return None, None, ""
    verified = payload.get("verified_field_count")
    changed = payload.get("changed_field_count")
    verified_count = verified if isinstance(verified, int) and not isinstance(verified, bool) else None
    changed_count = changed if isinstance(changed, int) and not isinstance(changed, bool) else None
    fields = payload.get("fields")
    mismatches: list[str] = []
    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue
            before_match = item.get("before_matches_parent")
            after_match = item.get("after_matches_current")
            if before_match is False or after_match is False:
                field = str(item.get("field", "unknown"))
                problems: list[str] = []
                if before_match is False:
                    problems.append("before!=parent")
                if after_match is False:
                    problems.append("after!=current")
                mismatches.append(f"{field}({'/'.join(problems)})")
    return verified_count, changed_count, ";".join(mismatches)


def load_correction_delta_diagnostics(
    status_path: str | Path = DEFAULT_STATUS_PATH,
    *,
    ticker: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Path, Path]:
    """Load correction catalysts and summarize their delta-certification states."""

    path = Path(status_path)
    status = _read_status(path)
    if status.get("status") != "completed":
        raise ValueError(
            "Latest pipeline status is not completed: "
            f"{status.get('status', 'missing')}"
        )
    directory = _decision_directory(status, path)
    catalysts_path = directory / "catalysts.csv"
    events_path = directory / "disclosure_events.csv"
    for required_path in (catalysts_path, events_path):
        if not required_path.is_file():
            raise ValueError(f"Decision artifact does not exist: {required_path}")

    dtype = {
        "ticker": "string",
        "rcept_no": "string",
        "correction_parent_rcept_no": "string",
        "correction_chain_root_rcept_no": "string",
    }
    catalysts = pd.read_csv(catalysts_path, dtype=dtype)
    events = pd.read_csv(events_path, dtype=dtype)
    required_catalyst = {
        "ticker",
        "rcept_no",
        "report_name",
        "is_correction",
        "correction_delta_status",
    }
    missing = sorted(required_catalyst - set(catalysts.columns))
    if missing:
        raise ValueError(
            "Catalyst diagnostics require newer decision artifacts. Missing: "
            + ", ".join(missing)
        )
    required_events = {
        "ticker",
        "rcept_no",
        "correction_lineage_status",
        "correction_chain_order",
        "correction_parent_rcept_no",
    }
    missing_events = sorted(required_events - set(events.columns))
    if missing_events:
        raise ValueError(
            "Disclosure lineage diagnostics are incomplete. Missing: "
            + ", ".join(missing_events)
        )

    for frame in (catalysts, events):
        frame["ticker"] = frame["ticker"].astype("string").str.strip().str.zfill(6)
        frame["rcept_no"] = frame["rcept_no"].astype("string").str.strip().str.zfill(14)

    correction_mask = catalysts["is_correction"].map(_as_bool)
    result = catalysts.loc[correction_mask].copy()
    if ticker is not None:
        result = result.loc[result["ticker"] == _ticker(ticker)].copy()

    lineage = events.loc[
        :,
        [
            "ticker",
            "rcept_no",
            "correction_lineage_status",
            "correction_chain_order",
            "correction_parent_rcept_no",
        ],
    ].rename(columns={"correction_parent_rcept_no": "lineage_parent_rcept_no"})
    result = result.drop(
        columns=[
            column
            for column in (
                "correction_lineage_status",
                "correction_chain_order",
                "lineage_parent_rcept_no",
            )
            if column in result.columns
        ]
    ).merge(lineage, on=["ticker", "rcept_no"], how="left", validate="one_to_one")

    details = result.get("correction_delta_json", pd.Series(index=result.index, dtype="string")).map(
        _delta_detail
    )
    result["verified_field_count"] = details.map(lambda item: item[0])
    result["changed_field_count"] = details.map(lambda item: item[1])
    result["mismatch_fields"] = details.map(lambda item: item[2])
    if "receipt_date" not in result.columns:
        result["receipt_date"] = ""
    available_columns = [column for column in _BASE_COLUMNS if column in result.columns]
    result = result.loc[:, available_columns].sort_values(
        ["ticker", "receipt_date", "rcept_no"],
        ascending=[True, False, False],
        kind="stable",
    ).reset_index(drop=True)

    if result.empty:
        summary = pd.DataFrame(columns=["ticker", "correction_delta_status", "count"])
    else:
        summary = (
            result.groupby(["ticker", "correction_delta_status"], dropna=False, sort=True)
            .size()
            .rename("count")
            .reset_index()
        )
    return result, summary, catalysts_path, events_path


def _render(frame: pd.DataFrame, output_format: str) -> str:
    if output_format == "json":
        return frame.to_json(orient="records", force_ascii=False, indent=2)
    if output_format == "csv":
        return frame.to_csv(index=False)
    return frame.to_string(index=False, na_rep="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-correction-delta-diagnostics",
        description="Show correction-delta certification states from the latest live run",
    )
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--ticker", type=_ticker)
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
        frame, summary, catalysts_path, events_path = load_correction_delta_diagnostics(
            args.status,
            ticker=args.ticker,
        )
        print(f"Catalysts: {catalysts_path}")
        print(f"Disclosure events: {events_path}")
        print(f"Correction catalysts: {len(frame)}")
        print("\nStatus summary")
        print(_render(summary, args.format) if not summary.empty else "No correction catalysts found.")
        if not frame.empty:
            print("\nCorrection details")
            print(_render(frame, args.format))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"correction-delta-diagnostics error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
