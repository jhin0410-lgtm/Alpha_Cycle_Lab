"""Cross-check KIS DATA rows against OpenDART historical actuals without scoring."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE

DEFAULT_EXPECTATION_ROOT = Path("data/private/live-research/expectation-intelligence")
DEFAULT_VALUATION_ROOT = Path("data/private/live-research/valuation-intelligence")
DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kis-expectation-semantic-crosscheck"
)
LATEST_POINTER_NAME = "latest_kis_expectation_semantic_crosscheck.json"
EXPECTED_SYMBOLS = ("000660", "005930")
TARGET_METRICS = ("revenue", "operating_income", "net_income")
OUTPUT_NAMES = ("output2", "output3")
SCALE_CANDIDATES = (1.0, 1e3, 1e4, 1e6, 1e8, 1e9, 1e12)
MAX_RELATIVE_ERROR = 0.005
MIN_SECOND_BEST_MEAN_ERROR = 0.01
_DATA_FIELD = re.compile(r"^data([1-9][0-9]*)$", re.IGNORECASE)
_PERIOD = re.compile(r"^(\d{4})\.(\d{2})(E)?$")


@dataclass(frozen=True)
class PeriodAxis:
    labels: tuple[str, ...]
    actual_years: tuple[int, ...]
    actual_fields_positional: tuple[str, ...]
    forecast_labels: tuple[str, ...]
    forecast_fields_positional: tuple[str, ...]


@dataclass(frozen=True)
class CandidateFit:
    output_name: str
    row_index: int
    metric: str
    scale: float
    year_to_field: tuple[tuple[int, str], ...]
    mean_relative_error: float
    max_relative_error: float
    second_best_mean_relative_error: float | None
    positional_mapping: bool
    unique_fit: bool
    verified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "output_name": self.output_name,
            "row_number_1_based": self.row_index + 1,
            "metric": self.metric,
            "scale_to_krw": self.scale,
            "year_to_field": {str(year): field for year, field in self.year_to_field},
            "observation_count": len(EXPECTED_SYMBOLS) * len(self.year_to_field),
            "issuer_count": len(EXPECTED_SYMBOLS),
            "mean_relative_error": self.mean_relative_error,
            "max_relative_error": self.max_relative_error,
            "second_best_mean_relative_error": self.second_best_mean_relative_error,
            "positional_mapping": self.positional_mapping,
            "unique_fit": self.unique_fit,
            "historical_actual_crosscheck_verified": self.verified,
            "provider_semantics_certified": False,
            "consensus_certified": False,
            "revision_certified": False,
            "decision_score_enabled": False,
        }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object, *, ensure_ascii: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=ensure_ascii, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _strict_false(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"{label} must keep {key}=false")


def _snapshot_id(mapping: Mapping[str, object], *, label: str) -> str:
    value = str(mapping.get("snapshot_id", "")).strip()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} snapshot_id must be a SHA-256 digest")
    return value


def _latest_snapshot(
    root: Path,
    *,
    required_files: Sequence[str],
    label: str,
) -> tuple[Path, dict[str, object]]:
    if not root.is_dir():
        raise ValueError(f"{label} root does not exist: {root}")
    for directory in sorted(root.iterdir(), reverse=True):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if not all((directory / name).is_file() for name in required_files):
            continue
        try:
            manifest = _read_object(directory / "manifest.json", label=f"{label} manifest")
        except ValueError:
            continue
        return directory, manifest
    raise ValueError(f"No complete {label} snapshot was found")


def _symbols(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} symbols must be an array")
    symbols = tuple(sorted(str(item).strip().zfill(6) for item in value))
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError(f"{label} symbols must be unique and non-empty")
    return symbols


def _rows(value: object, *, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(cast(Mapping[str, object], item))
    return tuple(rows)


def _data_fields(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    fields: list[tuple[int, str]] = []
    for key in {str(key) for row in rows for key in row}:
        match = _DATA_FIELD.fullmatch(key)
        if match is not None:
            fields.append((int(match.group(1)), key))
    fields.sort()
    return tuple(key for _, key in fields)


def _period_axis(payload: Mapping[str, object], *, symbol: str) -> PeriodAxis:
    rows = _rows(payload.get("output4"), label=f"{symbol}.output4")
    labels: list[str] = []
    for row in rows:
        if set(str(key) for key in row) != {"dt"}:
            raise ValueError(f"{symbol}.output4 must contain only dt")
        label = str(row.get("dt", "")).strip()
        if _PERIOD.fullmatch(label) is None:
            raise ValueError(f"Unsupported KIS period label for {symbol}: {label!r}")
        labels.append(label)
    if not labels or len(labels) != len(set(labels)):
        raise ValueError(f"KIS period labels must be unique and non-empty for {symbol}")

    actual_years: list[int] = []
    actual_fields: list[str] = []
    forecast_labels: list[str] = []
    forecast_fields: list[str] = []
    for index, label in enumerate(labels, start=1):
        match = _PERIOD.fullmatch(label)
        assert match is not None
        field = f"data{index}"
        if match.group(3):
            forecast_labels.append(label)
            forecast_fields.append(field)
        else:
            actual_years.append(int(match.group(1)))
            actual_fields.append(field)
    if len(actual_years) < 3:
        raise ValueError(f"KIS semantic crosscheck needs at least three actual years: {symbol}")
    return PeriodAxis(
        labels=tuple(labels),
        actual_years=tuple(actual_years),
        actual_fields_positional=tuple(actual_fields),
        forecast_labels=tuple(forecast_labels),
        forecast_fields_positional=tuple(forecast_fields),
    )


def _load_expectation(
    root: Path,
) -> tuple[Path, dict[str, object], dict[str, Mapping[str, object]], PeriodAxis]:
    directory, manifest = _latest_snapshot(
        root,
        required_files=("manifest.json", "raw_estimate_perform.json"),
        label="KIS expectation",
    )
    if manifest.get("provider") != "korea_investment_openapi":
        raise ValueError("KIS expectation manifest has unexpected provider")
    if manifest.get("source_scope") != KIS_RESEARCH_SOURCE_SCOPE:
        raise ValueError("KIS expectation manifest has unexpected source scope")
    if manifest.get("semantic_status") != "raw_structure_only":
        raise ValueError("KIS expectation snapshot is not semantically unclassified")
    for key in (
        "consensus_certified",
        "revision_certified",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(manifest, key, label="KIS expectation manifest")
    symbols = _symbols(manifest.get("symbols"), label="KIS expectation")
    if not set(EXPECTED_SYMBOLS).issubset(symbols):
        raise ValueError("KIS expectation snapshot is missing a required semiconductor issuer")
    _snapshot_id(manifest, label="KIS expectation")

    raw = _read_object(
        directory / "raw_estimate_perform.json",
        label="KIS raw estimate-perform",
    )
    payloads: dict[str, Mapping[str, object]] = {}
    axes: list[PeriodAxis] = []
    for symbol in EXPECTED_SYMBOLS:
        payload_raw = raw.get(symbol)
        if not isinstance(payload_raw, dict):
            raise ValueError(f"KIS raw payload is missing {symbol}")
        payload = cast(Mapping[str, object], payload_raw)
        for output_name in (*OUTPUT_NAMES, "output4"):
            if output_name not in payload:
                raise ValueError(f"KIS raw payload {symbol} is missing {output_name}")
        payloads[symbol] = payload
        axes.append(_period_axis(payload, symbol=symbol))
    if any(axis != axes[0] for axis in axes[1:]):
        raise ValueError("KIS period axes differ across issuers")
    return directory, manifest, payloads, axes[0]


def _history_years(manifest: Mapping[str, object]) -> int:
    value = manifest.get("history_years")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Valuation history_years must be an integer")
    if value < 3:
        raise ValueError("Valuation snapshot must contain at least three history years")
    return value


def _load_valuation(
    root: Path,
) -> tuple[Path, dict[str, object], pd.DataFrame]:
    directory, manifest = _latest_snapshot(
        root,
        required_files=("manifest.json", "financial_history.csv"),
        label="valuation",
    )
    _snapshot_id(manifest, label="valuation")
    _history_years(manifest)
    symbols = _symbols(manifest.get("symbols"), label="valuation")
    if not set(EXPECTED_SYMBOLS).issubset(symbols):
        raise ValueError("Valuation snapshot is missing a required semiconductor issuer")
    history = pd.read_csv(
        directory / "financial_history.csv",
        dtype={"ticker": "string"},
    )
    required = {"ticker", "business_year", "period_label"}
    for metric in TARGET_METRICS:
        required.update({metric, f"{metric}_prior_same"})
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"Valuation financial history is missing columns: {sorted(missing)}")
    history["ticker"] = history["ticker"].astype("string").str.zfill(6)
    history["business_year"] = pd.to_numeric(
        history["business_year"], errors="raise"
    ).astype(int)
    return directory, manifest, history


def _finite(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    result = float(numeric)
    return result if math.isfinite(result) else None


def _fy_row(history: pd.DataFrame, symbol: str, year: int) -> Mapping[str, object] | None:
    rows = history.loc[
        (history["ticker"] == symbol)
        & (history["business_year"] == year)
        & history["period_label"].astype(str).eq("FY")
    ]
    if rows.empty:
        return None
    if len(rows) != 1:
        raise ValueError(f"Valuation history has duplicate FY rows for {symbol} {year}")
    return cast(Mapping[str, object], rows.iloc[0].to_dict())


def _actual_lookup(
    history: pd.DataFrame,
    *,
    years: Sequence[int],
) -> tuple[dict[tuple[str, int, str], float], dict[str, object]]:
    values: dict[tuple[str, int, str], float] = {}
    basis: dict[str, object] = {}
    for symbol in EXPECTED_SYMBOLS:
        symbol_basis: dict[str, object] = {}
        for year in years:
            current = _fy_row(history, symbol, int(year))
            following = _fy_row(history, symbol, int(year) + 1)
            metric_basis: dict[str, str] = {}
            for metric in TARGET_METRICS:
                comparative = (
                    _finite(following.get(f"{metric}_prior_same"))
                    if following is not None
                    else None
                )
                direct = _finite(current.get(metric)) if current is not None else None
                if comparative is not None:
                    selected = comparative
                    source = f"{year + 1}_FY_prior_same"
                elif direct is not None:
                    selected = direct
                    source = f"{year}_FY_current"
                else:
                    raise ValueError(
                        f"Valuation history cannot resolve {metric} for {symbol} {year}"
                    )
                values[(symbol, int(year), metric)] = selected
                metric_basis[metric] = source
            symbol_basis[str(year)] = metric_basis
        basis[symbol] = symbol_basis
    return values, basis


def _number(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if text.casefold() in {"", "-", "--", "none", "nan", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        parsed = float(text)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return -parsed if negative else parsed


def _relative_error(observed: float, reference: float) -> float:
    denominator = max(abs(observed), abs(reference), 1.0)
    return abs(observed - reference) / denominator


def _fit_errors(
    payloads: Mapping[str, Mapping[str, object]],
    actuals: Mapping[tuple[str, int, str], float],
    *,
    output_name: str,
    row_index: int,
    metric: str,
    mapping: Sequence[tuple[int, str]],
    scale: float,
) -> tuple[float, ...] | None:
    errors: list[float] = []
    for symbol in EXPECTED_SYMBOLS:
        rows = _rows(payloads[symbol].get(output_name), label=f"{symbol}.{output_name}")
        if row_index >= len(rows):
            return None
        row = rows[row_index]
        for year, field in mapping:
            kis_value = _number(row.get(field))
            reference = actuals.get((symbol, year, metric))
            if kis_value is None or reference is None:
                return None
            errors.append(_relative_error(kis_value * scale, reference))
    return tuple(errors)


def _best_candidate(
    payloads: Mapping[str, Mapping[str, object]],
    actuals: Mapping[tuple[str, int, str], float],
    axis: PeriodAxis,
    *,
    output_name: str,
    row_index: int,
    metric: str,
) -> CandidateFit | None:
    shared_fields: tuple[str, ...] | None = None
    for symbol in EXPECTED_SYMBOLS:
        rows = _rows(payloads[symbol].get(output_name), label=f"{symbol}.{output_name}")
        if row_index >= len(rows):
            return None
        fields = _data_fields(rows)
        if shared_fields is None:
            shared_fields = fields
        elif fields != shared_fields:
            raise ValueError(f"KIS DATA fields differ across issuers for {output_name}")
    assert shared_fields is not None
    if len(shared_fields) != len(axis.labels):
        raise ValueError(
            f"KIS DATA-field count does not match period-axis count for {output_name}"
        )
    if len(shared_fields) < len(axis.actual_years):
        return None

    fits: list[tuple[float, float, float, tuple[tuple[int, str], ...]]] = []
    for field_permutation in itertools.permutations(shared_fields, len(axis.actual_years)):
        mapping = tuple(zip(axis.actual_years, field_permutation, strict=True))
        for scale in SCALE_CANDIDATES:
            errors = _fit_errors(
                payloads,
                actuals,
                output_name=output_name,
                row_index=row_index,
                metric=metric,
                mapping=mapping,
                scale=scale,
            )
            if errors is None:
                continue
            fits.append((max(errors), sum(errors) / len(errors), scale, mapping))
    if not fits:
        return None
    fits.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    best_max, best_mean, best_scale, best_mapping = fits[0]
    second_mean = fits[1][1] if len(fits) > 1 else None
    positional = best_mapping == tuple(
        zip(axis.actual_years, axis.actual_fields_positional, strict=True)
    )
    unique_fit = second_mean is None or second_mean >= MIN_SECOND_BEST_MEAN_ERROR
    verified = best_max <= MAX_RELATIVE_ERROR and positional and unique_fit
    return CandidateFit(
        output_name=output_name,
        row_index=row_index,
        metric=metric,
        scale=best_scale,
        year_to_field=best_mapping,
        mean_relative_error=round(best_mean, 8),
        max_relative_error=round(best_max, 8),
        second_best_mean_relative_error=(
            None if second_mean is None else round(second_mean, 8)
        ),
        positional_mapping=positional,
        unique_fit=unique_fit,
        verified=verified,
    )


def _discover_candidates(
    payloads: Mapping[str, Mapping[str, object]],
    actuals: Mapping[tuple[str, int, str], float],
    axis: PeriodAxis,
) -> tuple[list[CandidateFit], list[CandidateFit]]:
    all_candidates: list[CandidateFit] = []
    verified: list[CandidateFit] = []
    for output_name in OUTPUT_NAMES:
        shared_row_count = min(
            len(_rows(payloads[symbol].get(output_name), label=f"{symbol}.{output_name}"))
            for symbol in EXPECTED_SYMBOLS
        )
        for row_index in range(shared_row_count):
            for metric in TARGET_METRICS:
                candidate = _best_candidate(
                    payloads,
                    actuals,
                    axis,
                    output_name=output_name,
                    row_index=row_index,
                    metric=metric,
                )
                if candidate is not None:
                    all_candidates.append(candidate)
                    if candidate.verified:
                        verified.append(candidate)
    key = lambda item: (item.metric, item.max_relative_error, item.output_name, item.row_index)
    return sorted(all_candidates, key=key), sorted(verified, key=key)


def _metric_results(
    verified: Sequence[CandidateFit],
    axis: PeriodAxis,
) -> tuple[dict[str, object], int]:
    results: dict[str, object] = {}
    unique_count = 0
    for metric in TARGET_METRICS:
        matches = [item for item in verified if item.metric == metric]
        if len(matches) == 1:
            unique_count += 1
            match = matches[0]
            results[metric] = {
                "status": "unique_historical_actual_match",
                "output_name": match.output_name,
                "row_number_1_based": match.row_index + 1,
                "scale_to_krw": match.scale,
                "year_to_field": {
                    str(year): field for year, field in match.year_to_field
                },
                "mean_relative_error": match.mean_relative_error,
                "max_relative_error": match.max_relative_error,
                "forecast_period_labels": list(axis.forecast_labels),
                "forecast_fields_positional": list(axis.forecast_fields_positional),
                "forecast_values_published": False,
            }
        elif not matches:
            results[metric] = {"status": "no_verified_match"}
        else:
            results[metric] = {
                "status": "ambiguous_multiple_verified_matches",
                "match_count": len(matches),
            }
    return results, unique_count


def run_crosscheck(
    *,
    expectation_root: Path,
    valuation_root: Path,
    output_root: Path,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Crosscheck clock must be timezone-aware")
    expectation_dir, expectation_manifest, payloads, axis = _load_expectation(
        expectation_root
    )
    valuation_dir, valuation_manifest, history = _load_valuation(valuation_root)
    actuals, actual_basis = _actual_lookup(history, years=axis.actual_years)
    all_candidates, verified = _discover_candidates(payloads, actuals, axis)
    metric_results, unique_count = _metric_results(verified, axis)
    status = (
        "historical_actual_crosscheck_complete"
        if unique_count == len(TARGET_METRICS)
        else "historical_actual_crosscheck_partial"
    )

    captured_at = now.astimezone(UTC)
    payload_without_id: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "captured_at": captured_at.isoformat(),
        "expectation_snapshot_id": _snapshot_id(
            expectation_manifest,
            label="KIS expectation",
        ),
        "valuation_snapshot_id": _snapshot_id(valuation_manifest, label="valuation"),
        "expectation_directory": str(expectation_dir.resolve()),
        "valuation_directory": str(valuation_dir.resolve()),
        "symbols": list(EXPECTED_SYMBOLS),
        "actual_period_labels": [label for label in axis.labels if not label.endswith("E")],
        "forecast_period_labels": list(axis.forecast_labels),
        "positional_actual_fields": list(axis.actual_fields_positional),
        "positional_forecast_fields": list(axis.forecast_fields_positional),
        "actual_reference_policy": "prefer_following_fy_prior_same_then_direct_fy",
        "actual_reference_basis": actual_basis,
        "max_relative_error_threshold": MAX_RELATIVE_ERROR,
        "minimum_second_best_mean_error": MIN_SECOND_BEST_MEAN_ERROR,
        "scale_candidates_to_krw": list(SCALE_CANDIDATES),
        "metric_results": metric_results,
        "verified_candidates": [item.as_dict() for item in verified],
        "candidate_count_evaluated": len(all_candidates),
        "verified_candidate_count": len(verified),
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "point_in_time_backtest_eligible": False,
        "forecast_values_published": False,
        "decision_score_enabled": False,
    }
    artifact_id = hashlib.sha256(_canonical_bytes(payload_without_id)).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    directory.mkdir(parents=True, exist_ok=False)
    artifact = {**payload_without_id, "artifact_id": artifact_id}
    _write_json(directory / "crosscheck.json", artifact)
    pointer = {
        "status": status,
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "crosscheck_path": str((directory / "crosscheck.json").resolve()),
        "expectation_snapshot_id": artifact["expectation_snapshot_id"],
        "valuation_snapshot_id": artifact["valuation_snapshot_id"],
        "verified_candidate_count": len(verified),
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / LATEST_POINTER_NAME, pointer, ensure_ascii=True)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kis-expectation-semantic-crosscheck",
        description=(
            "Cross-check unclassified KIS DATA rows against local OpenDART valuation-history "
            "actuals without publishing forecast values or changing decision scores"
        ),
    )
    parser.add_argument("--expectation-root", type=Path, default=DEFAULT_EXPECTATION_ROOT)
    parser.add_argument("--valuation-root", type=Path, default=DEFAULT_VALUATION_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        pointer = run_crosscheck(
            expectation_root=args.expectation_root,
            valuation_root=args.valuation_root,
            output_root=args.output,
            now=datetime.now(UTC),
        )
        print(json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
