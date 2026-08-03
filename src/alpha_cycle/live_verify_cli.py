"""Fail-closed verification for the latest local live-research pipeline run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_STATUS_PATH = Path("data/private/live-research/latest_run.json")
_REQUIRED_DECISION_FILES = (
    "manifest.json",
    "financial_kpis.csv",
    "financial_kpi_mapping.csv",
    "disclosure_events.csv",
    "catalysts.csv",
    "disclosure_summary.csv",
    "macro_regime.csv",
    "market_context.csv",
    "valuation_metrics.csv",
    "financial_history.csv",
    "scorecards.csv",
    "decision_records.csv",
    "report.md",
)
_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "on"})
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationReport:
    status: str
    snapshot_id: str | None
    evaluation_date: str | None
    decision_directory: str | None
    checks_passed: int
    failures: tuple[str, ...]
    informational_warnings: tuple[str, ...]


def _read_json(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise ValueError(f"JSON file does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(Mapping[str, object], value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _string_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        try:
            result[str(key)] = int(raw)
        except (TypeError, ValueError):
            continue
    return result


def _as_bool(value: object) -> bool | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = str(value).strip().casefold()
    if text in _TRUE_VALUES:
        return True
    if text in {"", "0", "false", "f", "no", "n", "off", "none", "nan", "null"}:
        return False
    return None


def _resolve_path(raw: object, *, relative_to: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    return path if path.is_absolute() else (relative_to / path).resolve()


def _read_csv(path: Path, *, dtype: Mapping[str, str] | None = None) -> pd.DataFrame:
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    return pd.read_csv(path, dtype=dtype)


def verify_latest_run(status_path: str | Path = DEFAULT_STATUS_PATH) -> VerificationReport:
    """Verify linked live artifacts and active-catalyst invariants."""

    path = Path(status_path)
    failures: list[str] = []
    passed = 0
    try:
        status = _read_json(path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return VerificationReport(
            status="failed",
            snapshot_id=None,
            evaluation_date=None,
            decision_directory=None,
            checks_passed=0,
            failures=(str(exc),),
            informational_warnings=(),
        )

    snapshot_id = str(status.get("decision_snapshot_id", "")) or None
    evaluation_date = str(status.get("evaluation_date", "")) or None
    directory = _resolve_path(status.get("decision_directory"), relative_to=path.parent)

    def check(condition: bool, message: str) -> None:
        nonlocal passed
        if condition:
            passed += 1
        else:
            failures.append(message)

    check(status.get("status") == "completed", "latest run status is not completed")
    check(snapshot_id is not None and bool(_HEX_64.fullmatch(snapshot_id)), "invalid decision snapshot id")
    check(directory is not None and directory.is_dir(), "decision directory is missing")
    if directory is None or not directory.is_dir():
        return VerificationReport(
            status="failed",
            snapshot_id=snapshot_id,
            evaluation_date=evaluation_date,
            decision_directory=str(directory) if directory else None,
            checks_passed=passed,
            failures=tuple(failures),
            informational_warnings=tuple(_string_list(status.get("warnings"))),
        )

    missing_files = [name for name in _REQUIRED_DECISION_FILES if not (directory / name).is_file()]
    check(not missing_files, "missing decision files: " + ", ".join(missing_files))

    try:
        manifest = _read_json(directory / "manifest.json")
        catalysts = _read_csv(
            directory / "catalysts.csv",
            dtype={
                "ticker": "string",
                "rcept_no": "string",
                "correction_chain_root_rcept_no": "string",
            },
        )
        scorecards = _read_csv(directory / "scorecards.csv", dtype={"ticker": "string"})
        records = _read_csv(directory / "decision_records.csv", dtype={"ticker": "string"})
    except (ValueError, OSError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        failures.append(str(exc))
        return VerificationReport(
            status="failed",
            snapshot_id=snapshot_id,
            evaluation_date=evaluation_date,
            decision_directory=str(directory),
            checks_passed=passed,
            failures=tuple(failures),
            informational_warnings=tuple(_string_list(status.get("warnings"))),
        )

    check(manifest.get("snapshot_id") == snapshot_id, "status and manifest snapshot ids differ")
    check(manifest.get("evaluation_date") == evaluation_date, "status and manifest evaluation dates differ")

    expected_symbols = {value.zfill(6) for value in _string_list(status.get("decision_symbols"))}
    score_symbols = set(scorecards.get("ticker", pd.Series(dtype="string")).astype("string").str.zfill(6).dropna())
    record_symbols = set(records.get("ticker", pd.Series(dtype="string")).astype("string").str.zfill(6).dropna())
    check(bool(expected_symbols) and score_symbols == expected_symbols, "scorecard ticker set differs from status")
    check(record_symbols == expected_symbols, "decision-record ticker set differs from status")
    check(not scorecards.get("ticker", pd.Series(dtype="string")).duplicated().any(), "duplicate scorecard tickers")
    check(not records.get("ticker", pd.Series(dtype="string")).duplicated().any(), "duplicate decision-record tickers")

    expected_states = _string_mapping(status.get("decision_states"))
    actual_states = Counter(str(value) for value in scorecards.get("decision_state", pd.Series(dtype="string")).dropna())
    check(dict(actual_states) == expected_states, "decision-state counts differ from status")

    required_catalyst_columns = {
        "ticker",
        "rcept_no",
        "report_name",
        "receipt_date",
        "category",
        "priority",
        "is_correction",
        "is_latest_in_correction_chain",
    }
    missing_columns = sorted(required_catalyst_columns - set(catalysts.columns))
    check(not missing_columns, "catalysts missing columns: " + ", ".join(missing_columns))
    check(not catalysts.get("rcept_no", pd.Series(dtype="string")).duplicated().any(), "duplicate catalyst receipt numbers")

    if not missing_columns:
        latest_flags = catalysts["is_latest_in_correction_chain"].map(_as_bool)
        check(latest_flags.notna().all() and latest_flags.fillna(False).all(), "superseded disclosure remains in catalysts")

        roots = catalysts.get("correction_chain_root_rcept_no", pd.Series(dtype="string"))
        root_frame = pd.DataFrame({"ticker": catalysts["ticker"], "root": roots})
        root_frame = root_frame.loc[root_frame["root"].notna() & root_frame["root"].astype(str).ne("")]
        check(not root_frame.duplicated(["ticker", "root"]).any(), "multiple active catalysts share one correction lineage")

        if "is_material_correction" in catalysts.columns:
            correction = catalysts["is_correction"].map(_as_bool).fillna(False)
            material = catalysts["is_material_correction"].map(_as_bool).fillna(False)
            check((~correction | material).all(), "non-material correction remains in catalysts")

    valuation_scored = int(scorecards.get("valuation_score", pd.Series(dtype="float64")).notna().sum())
    try:
        expected_valuation_scored = int(status.get("valuation_scored_count", -1))
    except (TypeError, ValueError):
        expected_valuation_scored = -1
    check(valuation_scored == expected_valuation_scored, "valuation scored count differs from status")

    report_path = _resolve_path(status.get("report_path"), relative_to=path.parent)
    check(report_path is not None and report_path.is_file(), "report path is missing")
    if report_path is not None and report_path.is_file():
        report_text = report_path.read_text(encoding="utf-8")
        check(all(f"## {ticker}" in report_text for ticker in expected_symbols), "report is missing a decision ticker section")

    manifest_warnings = set(_string_list(manifest.get("warnings")))
    status_warnings = set(_string_list(status.get("warnings")))
    check(manifest_warnings == status_warnings, "status and manifest warnings differ")

    return VerificationReport(
        status="passed" if not failures else "failed",
        snapshot_id=snapshot_id,
        evaluation_date=evaluation_date,
        decision_directory=str(directory),
        checks_passed=passed,
        failures=tuple(failures),
        informational_warnings=tuple(sorted(status_warnings)),
    )


def _write_report(report: VerificationReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-live-verify",
        description="Verify the latest local live pipeline artifacts",
    )
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_latest_run(args.status)
    output = args.output or args.status.parent / "latest_verification.json"
    _write_report(report, output)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    elif report.status == "passed":
        print("LIVE VERIFICATION: PASS")
        print(f"snapshot: {report.snapshot_id}")
        print(f"checks passed: {report.checks_passed}")
        print(f"informational warnings: {len(report.informational_warnings)}")
        print(f"verification artifact: {output}")
    else:
        print("LIVE VERIFICATION: FAIL", file=sys.stderr)
        for failure in report.failures:
            print(f"- {failure}", file=sys.stderr)
        print(f"verification artifact: {output}", file=sys.stderr)
    return 0 if report.status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
