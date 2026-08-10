"""Cross-check KIS net-income row against OpenDART owners-of-parent profit/loss."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.kis_expectation_semantic_crosscheck_cli import (
    DEFAULT_EXPECTATION_ROOT,
    DEFAULT_VALUATION_ROOT,
    EXPECTED_SYMBOLS,
    OUTPUT_NAMES,
    _best_candidate,
    _load_expectation,
    _load_valuation,
    _read_object,
    _rows,
    _snapshot_id,
)

DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kis-owner-net-income-crosscheck"
)
LATEST_POINTER_NAME = "latest_kis_owner_net_income_crosscheck.json"
OWNER_NET_INCOME_METRIC = "net_income_attributable_to_owners"
OWNER_NET_INCOME_ACCOUNT_ID = "ifrs-full_ProfitLossAttributableToOwnersOfParent"
_NORMALIZED_OWNER_ACCOUNT_ID = re.sub(
    r"[^0-9a-z]+", "", OWNER_NET_INCOME_ACCOUNT_ID.casefold()
)


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


def _normalized(value: object) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value).strip().casefold())


def _amount(value: object) -> float | None:
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


def _valuation_raw(valuation_directory: Path) -> Mapping[str, object]:
    path = valuation_directory / "raw_valuation.json"
    payload = _read_object(path, label="valuation raw_valuation")
    return cast(Mapping[str, object], payload)


def _financial_periods(
    raw_valuation: Mapping[str, object],
    symbol: str,
) -> tuple[Mapping[str, object], ...]:
    company = raw_valuation.get(symbol)
    if not isinstance(company, dict):
        raise ValueError(f"Valuation raw payload is missing issuer {symbol}")
    periods_raw = company.get("financial_periods")
    if not isinstance(periods_raw, list):
        raise ValueError(f"Valuation raw payload is missing financial_periods for {symbol}")
    periods: list[Mapping[str, object]] = []
    for index, value in enumerate(periods_raw):
        if not isinstance(value, dict):
            raise ValueError(f"{symbol}.financial_periods[{index}] must be an object")
        periods.append(cast(Mapping[str, object], value))
    return tuple(periods)


def _fy_period(
    periods: Sequence[Mapping[str, object]],
    *,
    symbol: str,
    business_year: int,
) -> Mapping[str, object] | None:
    matches = [
        period
        for period in periods
        if int(str(period.get("business_year", "0"))) == business_year
        and str(period.get("report_code", "")).strip() == "11011"
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"Duplicate FY raw valuation periods for {symbol} {business_year}")
    return matches[0]


def _payload_rows(
    period: Mapping[str, object],
    *,
    symbol: str,
    year: int,
) -> tuple[Mapping[str, object], ...]:
    payload = period.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"Raw valuation FY payload is invalid for {symbol} {year}")
    raw_rows = payload.get("list")
    if not isinstance(raw_rows, list):
        raise ValueError(f"Raw valuation FY list is invalid for {symbol} {year}")
    rows: list[Mapping[str, object]] = []
    for index, value in enumerate(raw_rows):
        if not isinstance(value, dict):
            raise ValueError(f"Raw valuation row is invalid for {symbol} {year} #{index}")
        rows.append(cast(Mapping[str, object], value))
    return tuple(rows)


def _owner_row(
    period: Mapping[str, object],
    *,
    symbol: str,
    year: int,
) -> Mapping[str, object]:
    candidates = [
        row
        for row in _payload_rows(period, symbol=symbol, year=year)
        if _normalized(row.get("account_id")) == _NORMALIZED_OWNER_ACCOUNT_ID
        and str(row.get("sj_div", "")).strip().upper() in {"IS", "CIS"}
    ]
    if not candidates:
        raise ValueError(
            f"OpenDART owner-attributable net-income account not found for {symbol} {year}"
        )
    if len(candidates) > 1:
        plain = [
            row
            for row in candidates
            if str(row.get("account_detail", "")).strip() in {"", "-"}
        ]
        candidates = plain or candidates
    if len(candidates) != 1:
        raise ValueError(
            f"OpenDART owner-attributable net-income account is ambiguous for {symbol} {year}"
        )
    return candidates[0]


def _owner_actuals(
    raw_valuation: Mapping[str, object],
    *,
    years: Sequence[int],
) -> tuple[dict[tuple[str, int, str], float], dict[str, object]]:
    actuals: dict[tuple[str, int, str], float] = {}
    basis: dict[str, object] = {}
    for symbol in EXPECTED_SYMBOLS:
        periods = _financial_periods(raw_valuation, symbol)
        symbol_basis: dict[str, object] = {}
        for year in years:
            current = _fy_period(periods, symbol=symbol, business_year=int(year))
            following = _fy_period(
                periods,
                symbol=symbol,
                business_year=int(year) + 1,
            )
            selected: float | None = None
            source: str | None = None
            account_name: str | None = None
            if following is not None:
                row = _owner_row(
                    following,
                    symbol=symbol,
                    year=int(year) + 1,
                )
                comparative = _amount(row.get("frmtrm_amount"))
                if comparative is not None:
                    selected = comparative
                    source = f"{year + 1}_FY_prior_same"
                    account_name = str(row.get("account_nm", "")).strip() or None
            if selected is None and current is not None:
                row = _owner_row(current, symbol=symbol, year=int(year))
                direct = _amount(row.get("thstrm_amount"))
                if direct is not None:
                    selected = direct
                    source = f"{year}_FY_current"
                    account_name = str(row.get("account_nm", "")).strip() or None
            if selected is None or source is None:
                raise ValueError(
                    f"OpenDART cannot resolve owner-attributable net income for {symbol} {year}"
                )
            actuals[(symbol, int(year), OWNER_NET_INCOME_METRIC)] = selected
            symbol_basis[str(year)] = {
                "source": source,
                "account_id": OWNER_NET_INCOME_ACCOUNT_ID,
                "account_name": account_name,
            }
        basis[symbol] = symbol_basis
    return actuals, basis


def _discover_owner_matches(
    payloads: Mapping[str, Mapping[str, object]],
    actuals: Mapping[tuple[str, int, str], float],
    axis: object,
) -> list[object]:
    matches: list[object] = []
    for output_name in OUTPUT_NAMES:
        shared_row_count = min(
            len(_rows(payloads[symbol].get(output_name), label=f"{symbol}.{output_name}"))
            for symbol in EXPECTED_SYMBOLS
        )
        for row_index in range(shared_row_count):
            candidate = _best_candidate(
                payloads,
                actuals,
                axis,
                output_name=output_name,
                row_index=row_index,
                metric=OWNER_NET_INCOME_METRIC,
            )
            if candidate is not None and candidate.verified:
                matches.append(candidate)
    return matches


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
    valuation_dir, valuation_manifest, _ = _load_valuation(valuation_root)
    raw_valuation = _valuation_raw(valuation_dir)
    actuals, basis = _owner_actuals(raw_valuation, years=axis.actual_years)
    matches = _discover_owner_matches(payloads, actuals, axis)

    if len(matches) == 1:
        match = matches[0]
        metric_result: dict[str, object] = {
            "status": "unique_historical_actual_match",
            "output_name": match.output_name,
            "row_number_1_based": match.row_index + 1,
            "scale_to_krw": match.scale,
            "year_to_field": {str(year): field for year, field in match.year_to_field},
            "mean_relative_error": match.mean_relative_error,
            "max_relative_error": match.max_relative_error,
            "forecast_period_labels": list(axis.forecast_labels),
            "forecast_fields_positional": list(axis.forecast_fields_positional),
            "forecast_values_published": False,
        }
        status = "owner_net_income_historical_match_verified"
    elif not matches:
        metric_result = {"status": "no_verified_match"}
        status = "owner_net_income_historical_match_unresolved"
    else:
        metric_result = {
            "status": "ambiguous_multiple_verified_matches",
            "match_count": len(matches),
        }
        status = "owner_net_income_historical_match_ambiguous"

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
        "metric": OWNER_NET_INCOME_METRIC,
        "authoritative_reference_account_id": OWNER_NET_INCOME_ACCOUNT_ID,
        "actual_reference_basis": basis,
        "metric_result": metric_result,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "point_in_time_backtest_eligible": False,
        "forecast_values_published": False,
        "decision_score_enabled": False,
        "order_api_enabled": False,
    }
    artifact_id = hashlib.sha256(_canonical_bytes(payload_without_id)).hexdigest()
    artifact = {**payload_without_id, "artifact_id": artifact_id}
    directory = output_root / f"{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}__{artifact_id[:12]}"
    directory.mkdir(parents=True, exist_ok=False)
    artifact_path = directory / "crosscheck.json"
    _write_json(artifact_path, artifact)
    pointer = {
        "status": status,
        "artifact_id": artifact_id,
        "crosscheck_path": str(artifact_path.resolve()),
        "artifact_directory": str(directory.resolve()),
        "expectation_snapshot_id": payload_without_id["expectation_snapshot_id"],
        "valuation_snapshot_id": payload_without_id["valuation_snapshot_id"],
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
        prog="alpha-cycle-kis-owner-net-income-crosscheck",
        description=(
            "Cross-check KIS rows against OpenDART profit/loss attributable to owners "
            "of the parent without publishing forecast values or changing scores."
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
        payload = run_crosscheck(
            expectation_root=args.expectation_root,
            valuation_root=args.valuation_root,
            output_root=args.output,
            now=datetime.now(UTC),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
