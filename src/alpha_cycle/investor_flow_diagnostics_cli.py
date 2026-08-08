"""Non-scoring diagnostics for the latest Kiwoom investor-flow export."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_POINTER = Path(
    "data/private/live-research/kiwoom-openapi-plus-investor-flow/"
    "latest_investor_flow_export.json"
)
WINDOWS = (5, 20)


@dataclass(frozen=True)
class FlowWindowSummary:
    ticker: str
    window: int
    observations: int
    latest_date: str
    oldest_date: str
    latest_price_abs: int | None
    oldest_price_abs: int | None
    price_return_pct: float | None
    cumulative_volume: int | None
    individual_net_buy_shares: int | None
    foreign_net_buy_shares: int | None
    institution_net_buy_shares: int | None
    pension_net_buy_shares: int | None
    foreign_institution_net_buy_shares: int | None
    foreign_institution_volume_ratio: float | None
    descriptive_state: str
    decision_score_enabled: bool = False


@dataclass(frozen=True)
class TickerDiagnostics:
    ticker: str
    row_count: int
    date_order_descending: bool
    positive_normalized_price_rows: int
    comparable_market_balance_rows: int
    exact_market_balance_rows: int
    max_abs_market_balance_residual_shares: int | None
    comparable_institution_breakdown_rows: int
    exact_institution_breakdown_rows: int
    max_abs_institution_breakdown_residual_shares: int | None


@dataclass(frozen=True)
class FlowDiagnosticsReport:
    status: str
    source_scope: str
    snapshot_id: str
    semantic_status: str
    request_contract_status: str
    semantics_certified: bool
    decision_score_enabled: bool
    tickers: tuple[TickerDiagnostics, ...]
    windows: tuple[FlowWindowSummary, ...]


def _integer(raw: object) -> int | None:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _sum_present(rows: Iterable[dict[str, str]], key: str) -> int | None:
    values = [_integer(row.get(key, "")) for row in rows]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _price_abs(row: dict[str, str]) -> int | None:
    value = _integer(row.get("current_price", ""))
    return None if value is None else abs(value)


def _descriptive_state(price_return_pct: float | None, combined_flow: int | None) -> str:
    if price_return_pct is None or combined_flow is None:
        return "insufficient_evidence"
    if price_return_pct > 0 and combined_flow > 0:
        return "demand_confirmation"
    if price_return_pct < 0 and combined_flow < 0:
        return "distribution_confirmation"
    if price_return_pct < 0 and combined_flow > 0:
        return "accumulation_divergence"
    if price_return_pct > 0 and combined_flow < 0:
        return "selling_divergence"
    return "mixed_or_flat"


def _window_summary(ticker: str, rows: list[dict[str, str]], window: int) -> FlowWindowSummary:
    selected = rows[:window]
    latest = selected[0]
    oldest = selected[-1]
    latest_price = _price_abs(latest)
    oldest_price = _price_abs(oldest)
    price_return_pct: float | None = None
    if latest_price is not None and oldest_price is not None and oldest_price != 0:
        price_return_pct = (latest_price / oldest_price - 1.0) * 100.0

    volume = _sum_present(selected, "cumulative_volume")
    individual = _sum_present(selected, "individual_net_buy_shares")
    foreign = _sum_present(selected, "foreign_net_buy_shares")
    institution = _sum_present(selected, "institution_net_buy_shares")
    pension = _sum_present(selected, "pension_net_buy_shares")
    combined = foreign + institution if foreign is not None and institution is not None else None
    ratio = (
        combined / volume
        if combined is not None and volume is not None and volume != 0
        else None
    )
    state = (
        _descriptive_state(price_return_pct, combined)
        if len(selected) >= window
        else "insufficient_history"
    )
    return FlowWindowSummary(
        ticker=ticker,
        window=window,
        observations=len(selected),
        latest_date=latest.get("date", ""),
        oldest_date=oldest.get("date", ""),
        latest_price_abs=latest_price,
        oldest_price_abs=oldest_price,
        price_return_pct=price_return_pct,
        cumulative_volume=volume,
        individual_net_buy_shares=individual,
        foreign_net_buy_shares=foreign,
        institution_net_buy_shares=institution,
        pension_net_buy_shares=pension,
        foreign_institution_net_buy_shares=combined,
        foreign_institution_volume_ratio=ratio,
        descriptive_state=state,
    )


def _row_sum(row: dict[str, str], keys: tuple[str, ...]) -> int | None:
    values = [_integer(row.get(key, "")) for key in keys]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _ticker_diagnostics(ticker: str, rows: list[dict[str, str]]) -> TickerDiagnostics:
    dates = [row.get("date", "") for row in rows]
    market_residuals: list[int] = []
    institution_residuals: list[int] = []
    institution_parts = (
        "financial_investment_net_buy_shares",
        "insurance_net_buy_shares",
        "investment_trust_net_buy_shares",
        "other_finance_net_buy_shares",
        "bank_net_buy_shares",
        "pension_net_buy_shares",
        "private_fund_net_buy_shares",
        "state_net_buy_shares",
    )
    for row in rows:
        market_total = _row_sum(
            row,
            (
                "individual_net_buy_shares",
                "foreign_net_buy_shares",
                "institution_net_buy_shares",
                "other_corporation_net_buy_shares",
                "domestic_foreign_net_buy_shares",
            ),
        )
        if market_total is not None:
            market_residuals.append(market_total)
        institution = _integer(row.get("institution_net_buy_shares", ""))
        parts = _row_sum(row, institution_parts)
        if institution is not None and parts is not None:
            institution_residuals.append(institution - parts)

    return TickerDiagnostics(
        ticker=ticker,
        row_count=len(rows),
        date_order_descending=dates == sorted(dates, reverse=True),
        positive_normalized_price_rows=sum(1 for row in rows if (_price_abs(row) or 0) > 0),
        comparable_market_balance_rows=len(market_residuals),
        exact_market_balance_rows=sum(value == 0 for value in market_residuals),
        max_abs_market_balance_residual_shares=(
            max((abs(value) for value in market_residuals), default=0)
            if market_residuals
            else None
        ),
        comparable_institution_breakdown_rows=len(institution_residuals),
        exact_institution_breakdown_rows=sum(value == 0 for value in institution_residuals),
        max_abs_institution_breakdown_residual_shares=(
            max((abs(value) for value in institution_residuals), default=0)
            if institution_residuals
            else None
        ),
    )


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _request_contract_status(manifest: dict[str, object]) -> str:
    expected: dict[str, object] = {
        "amount_quantity_type": "2",
        "trade_type": "0",
        "unit_type": "1",
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            return f"contract_mismatch:{key}"
    return "verified_net_buy_quantity_single_share_unscored"


def build_report(pointer_path: Path = DEFAULT_POINTER) -> FlowDiagnosticsReport:
    pointer = _read_json(pointer_path)
    csv_path = Path(str(pointer.get("investor_flows_path", "")))
    manifest_path = Path(str(pointer.get("manifest_path", "")))
    if not csv_path.is_file():
        raise FileNotFoundError(f"investor-flow CSV not found: {csv_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"investor-flow manifest not found: {manifest_path}")

    manifest = _read_json(manifest_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("investor-flow CSV is empty")

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = row.get("ticker", "").strip()
        if ticker:
            grouped.setdefault(ticker, []).append(row)
    if not grouped:
        raise ValueError("investor-flow CSV has no ticker rows")

    diagnostics: list[TickerDiagnostics] = []
    windows: list[FlowWindowSummary] = []
    for ticker, ticker_rows in grouped.items():
        diagnostics.append(_ticker_diagnostics(ticker, ticker_rows))
        windows.extend(_window_summary(ticker, ticker_rows, window) for window in WINDOWS)

    return FlowDiagnosticsReport(
        status="completed",
        source_scope=str(pointer.get("source_scope", "")),
        snapshot_id=str(pointer.get("snapshot_id", "")),
        semantic_status=str(pointer.get("semantic_status", "")),
        request_contract_status=_request_contract_status(manifest),
        semantics_certified=False,
        decision_score_enabled=False,
        tickers=tuple(diagnostics),
        windows=tuple(windows),
    )


def _print_report(report: FlowDiagnosticsReport) -> None:
    print("KIWOOM INVESTOR FLOW LIVE DIAGNOSTICS")
    print(f"snapshot: {report.snapshot_id}")
    print(f"request contract: {report.request_contract_status}")
    print("semantics certified: false")
    print("decision score: disabled")
    print()
    for diag in report.tickers:
        print(
            f"{diag.ticker}: rows={diag.row_count} "
            f"date_desc={str(diag.date_order_descending).lower()} "
            f"price_rows={diag.positive_normalized_price_rows}/{diag.row_count} "
            f"market_balance_exact={diag.exact_market_balance_rows}/"
            f"{diag.comparable_market_balance_rows} "
            f"market_balance_max_abs={diag.max_abs_market_balance_residual_shares} "
            f"institution_breakdown_exact={diag.exact_institution_breakdown_rows}/"
            f"{diag.comparable_institution_breakdown_rows} "
            f"institution_breakdown_max_abs={diag.max_abs_institution_breakdown_residual_shares}"
        )
    print()
    for row in report.windows:
        return_text = "n/a" if row.price_return_pct is None else f"{row.price_return_pct:.2f}%"
        ratio_text = (
            "n/a"
            if row.foreign_institution_volume_ratio is None
            else f"{row.foreign_institution_volume_ratio * 100.0:.2f}%"
        )
        print(
            f"{row.ticker} {row.window}d: price={return_text} "
            f"foreign={row.foreign_net_buy_shares} "
            f"institution={row.institution_net_buy_shares} "
            f"foreign+institution={row.foreign_institution_net_buy_shares} "
            f"flow/volume={ratio_text} state={row.descriptive_state}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and summarize the latest unscored Kiwoom investor-flow artifact"
    )
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.pointer)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"KIWOOM INVESTOR FLOW LIVE DIAGNOSTICS: FAIL: {exc}")
        return 2
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
