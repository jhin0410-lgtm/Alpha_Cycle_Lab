"""Verified, non-scoring Kiwoom investor-flow evidence for decision snapshots.

The source artifact is the immutable OPT10059 export. This module never rewrites
that artifact. It verifies the live request contract, reconciles provider fields,
checks point-in-time binding, derives short flow windows, and attaches the result
as informational evidence without changing any decision score.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

SOURCE_SCOPE = "kiwoom_openapi_plus_opt10059_net_buy_quantity"
EXPECTED_TICKERS = ("005930", "000660")
WINDOWS = (5, 20)
VERIFIED_REQUEST_CONTRACT = "verified_net_buy_quantity_single_share_unscored"


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
    rows_on_or_before_evaluation_date: int


@dataclass(frozen=True)
class InvestorFlowEvidence:
    status: str
    reason: str
    source_scope: str
    snapshot_id: str
    provider_semantic_status: str
    request_contract_status: str
    field_mapping_verified: bool
    point_in_time_verified: bool
    evidence_verified: bool
    decision_score_enabled: bool
    evaluation_date: str
    reference_date: str
    captured_date: str
    tickers: tuple[TickerDiagnostics, ...]
    windows: tuple[FlowWindowSummary, ...]

    def window(self, ticker: str, window: int) -> FlowWindowSummary | None:
        normalized = str(ticker).zfill(6)
        return next(
            (
                row
                for row in self.windows
                if row.ticker == normalized and row.window == window
            ),
            None,
        )



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



def _window_summary(
    ticker: str,
    rows: list[dict[str, str]],
    window: int,
) -> FlowWindowSummary:
    selected = rows[:window]
    if not selected:
        return FlowWindowSummary(
            ticker=ticker,
            window=window,
            observations=0,
            latest_date="",
            oldest_date="",
            latest_price_abs=None,
            oldest_price_abs=None,
            price_return_pct=None,
            cumulative_volume=None,
            individual_net_buy_shares=None,
            foreign_net_buy_shares=None,
            institution_net_buy_shares=None,
            pension_net_buy_shares=None,
            foreign_institution_net_buy_shares=None,
            foreign_institution_volume_ratio=None,
            descriptive_state="insufficient_history",
        )
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
    combined = (
        foreign + institution
        if foreign is not None and institution is not None
        else None
    )
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



def _ticker_diagnostics(
    ticker: str,
    rows: list[dict[str, str]],
    evaluation_date: date,
) -> TickerDiagnostics:
    dates = [row.get("date", "") for row in rows]
    cutoff = evaluation_date.strftime("%Y%m%d")
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
        positive_normalized_price_rows=sum(
            1 for row in rows if (_price_abs(row) or 0) > 0
        ),
        comparable_market_balance_rows=len(market_residuals),
        exact_market_balance_rows=sum(value == 0 for value in market_residuals),
        max_abs_market_balance_residual_shares=(
            max((abs(value) for value in market_residuals), default=0)
            if market_residuals
            else None
        ),
        comparable_institution_breakdown_rows=len(institution_residuals),
        exact_institution_breakdown_rows=sum(
            value == 0 for value in institution_residuals
        ),
        max_abs_institution_breakdown_residual_shares=(
            max((abs(value) for value in institution_residuals), default=0)
            if institution_residuals
            else None
        ),
        rows_on_or_before_evaluation_date=sum(
            bool(value) and value <= cutoff for value in dates
        ),
    )



def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], payload)



def _request_contract_status(manifest: dict[str, object]) -> str:
    expected: dict[str, object] = {
        "amount_quantity_type": "2",
        "trade_type": "0",
        "unit_type": "1",
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            return f"contract_mismatch:{key}"
    return VERIFIED_REQUEST_CONTRACT



def _field_mapping_reason(
    *,
    source_scope: str,
    pointer_snapshot_id: str,
    manifest: dict[str, object],
    diagnostics: Sequence[TickerDiagnostics],
    expected_tickers: tuple[str, ...],
    row_count: int,
) -> str:
    if source_scope != SOURCE_SCOPE or str(manifest.get("source_scope", "")) != SOURCE_SCOPE:
        return "source_scope_mismatch"
    if pointer_snapshot_id != str(manifest.get("snapshot_id", "")):
        return "snapshot_id_mismatch"
    if int(manifest.get("record_count", -1)) != row_count:
        return "record_count_mismatch"
    if _request_contract_status(manifest) != VERIFIED_REQUEST_CONTRACT:
        return _request_contract_status(manifest)
    observed = tuple(sorted(diag.ticker for diag in diagnostics))
    if observed != tuple(sorted(expected_tickers)):
        return "ticker_set_mismatch"
    for diag in diagnostics:
        if diag.row_count < max(WINDOWS):
            return f"insufficient_history:{diag.ticker}"
        if not diag.date_order_descending:
            return f"date_order_mismatch:{diag.ticker}"
        if diag.positive_normalized_price_rows != diag.row_count:
            return f"invalid_price_rows:{diag.ticker}"
        if (
            diag.comparable_market_balance_rows != diag.row_count
            or diag.exact_market_balance_rows != diag.row_count
            or diag.max_abs_market_balance_residual_shares != 0
        ):
            return f"market_balance_mismatch:{diag.ticker}"
        if (
            diag.comparable_institution_breakdown_rows != diag.row_count
            or diag.exact_institution_breakdown_rows != diag.row_count
            or diag.max_abs_institution_breakdown_residual_shares != 0
        ):
            return f"institution_breakdown_mismatch:{diag.ticker}"
    return "verified_live_field_mapping"



def _point_in_time_reason(
    manifest: dict[str, object],
    diagnostics: Sequence[TickerDiagnostics],
    evaluation_date: date,
) -> str:
    expected_date = evaluation_date.strftime("%Y%m%d")
    if str(manifest.get("reference_date", "")) != expected_date:
        return "reference_date_mismatch"
    captured_at = str(manifest.get("captured_at", ""))
    if captured_at[:10] != evaluation_date.isoformat():
        return "captured_date_mismatch"
    for diag in diagnostics:
        if diag.rows_on_or_before_evaluation_date != diag.row_count:
            return f"future_flow_row:{diag.ticker}"
    return "verified_live_point_in_time"



def load_investor_flow_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    expected_tickers: Sequence[str] = EXPECTED_TICKERS,
) -> InvestorFlowEvidence:
    """Load and verify one live investor-flow artifact without mutating it."""

    pointer = _read_json(Path(pointer_path))
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

    expected = tuple(dict.fromkeys(str(value).zfill(6) for value in expected_tickers))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        ticker = row.get("ticker", "").strip().zfill(6)
        if ticker:
            grouped.setdefault(ticker, []).append(row)
    if not grouped:
        raise ValueError("investor-flow CSV has no ticker rows")

    diagnostics = tuple(
        _ticker_diagnostics(ticker, ticker_rows, evaluation_date)
        for ticker, ticker_rows in sorted(grouped.items())
    )
    mapping_reason = _field_mapping_reason(
        source_scope=str(pointer.get("source_scope", "")),
        pointer_snapshot_id=str(pointer.get("snapshot_id", "")),
        manifest=manifest,
        diagnostics=diagnostics,
        expected_tickers=expected,
        row_count=len(rows),
    )
    point_reason = _point_in_time_reason(manifest, diagnostics, evaluation_date)
    field_mapping_verified = mapping_reason == "verified_live_field_mapping"
    point_in_time_verified = point_reason == "verified_live_point_in_time"
    evidence_verified = field_mapping_verified and point_in_time_verified

    windows: list[FlowWindowSummary] = []
    cutoff = evaluation_date.strftime("%Y%m%d")
    for ticker, ticker_rows in sorted(grouped.items()):
        eligible = [row for row in ticker_rows if row.get("date", "") <= cutoff]
        windows.extend(
            _window_summary(ticker, eligible, window)
            for window in WINDOWS
        )

    reason = (
        "verified_live_evidence"
        if evidence_verified
        else mapping_reason if not field_mapping_verified else point_reason
    )
    return InvestorFlowEvidence(
        status="verified" if evidence_verified else "unverified",
        reason=reason,
        source_scope=str(pointer.get("source_scope", "")),
        snapshot_id=str(pointer.get("snapshot_id", "")),
        provider_semantic_status=str(pointer.get("semantic_status", "")),
        request_contract_status=_request_contract_status(manifest),
        field_mapping_verified=field_mapping_verified,
        point_in_time_verified=point_in_time_verified,
        evidence_verified=evidence_verified,
        decision_score_enabled=False,
        evaluation_date=evaluation_date.isoformat(),
        reference_date=str(manifest.get("reference_date", "")),
        captured_date=str(manifest.get("captured_at", ""))[:10],
        tickers=diagnostics,
        windows=tuple(windows),
    )



def attach_investor_flow_to_scorecards(
    scorecards: pd.DataFrame,
    evidence: InvestorFlowEvidence,
) -> pd.DataFrame:
    """Attach verified informational flow fields without touching score columns."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["investor_flow_snapshot_id"] = evidence.snapshot_id
    result["investor_flow_provider_semantic_status"] = evidence.provider_semantic_status
    result["investor_flow_field_mapping_verified"] = evidence.field_mapping_verified
    result["investor_flow_point_in_time_verified"] = evidence.point_in_time_verified
    result["investor_flow_evidence_verified"] = evidence.evidence_verified
    result["investor_flow_score_enabled"] = False
    result["investor_flow_evidence_reason"] = evidence.reason

    for window in WINDOWS:
        lookup = {
            row.ticker: row
            for row in evidence.windows
            if row.window == window
        }
        prefix = f"investor_flow_{window}d_"
        result[prefix + "state"] = result["ticker"].map(
            lambda ticker: (
                lookup[str(ticker)].descriptive_state
                if evidence.evidence_verified and str(ticker) in lookup
                else "unverified"
            )
        )
        for suffix, attribute in (
            ("price_return_pct", "price_return_pct"),
            ("foreign_net_buy_shares", "foreign_net_buy_shares"),
            ("institution_net_buy_shares", "institution_net_buy_shares"),
            ("foreign_institution_net_buy_shares", "foreign_institution_net_buy_shares"),
            ("foreign_institution_volume_ratio", "foreign_institution_volume_ratio"),
        ):
            result[prefix + suffix] = result["ticker"].map(
                lambda ticker, attr=attribute: (
                    getattr(lookup[str(ticker)], attr)
                    if evidence.evidence_verified and str(ticker) in lookup
                    else None
                )
            )
    return result



def attach_investor_flow_to_records(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    """Copy compact investor-flow evidence fields into decision records."""

    prefixes = (
        "investor_flow_snapshot_id",
        "investor_flow_provider_semantic_status",
        "investor_flow_field_mapping_verified",
        "investor_flow_point_in_time_verified",
        "investor_flow_evidence_verified",
        "investor_flow_score_enabled",
        "investor_flow_evidence_reason",
        "investor_flow_5d_",
        "investor_flow_20d_",
    )
    columns = [
        column
        for column in scorecards.columns
        if column == "ticker" or any(column.startswith(prefix) for prefix in prefixes)
    ]
    if "ticker" not in columns:
        raise ValueError("Scorecards are missing ticker")
    supplement = scorecards.loc[:, columns].copy()
    return records.merge(supplement, on="ticker", how="left", validate="one_to_one")



def _format_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2f}%"



def _format_ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100.0:+.2f}%"



def append_investor_flow_report(
    report: str,
    evidence: InvestorFlowEvidence,
) -> str:
    """Append transparent, non-scoring foreign/institution flow evidence."""

    lines = [
        report.rstrip(),
        "",
        "## 외국인·기관 수급 증거 (비점수)",
        "",
        f"- evidence status: `{evidence.status}` / reason `{evidence.reason}`",
        f"- snapshot: `{evidence.snapshot_id}`",
        f"- provider raw semantic status: `{evidence.provider_semantic_status}`",
        f"- field mapping verified: `{str(evidence.field_mapping_verified).lower()}`",
        f"- point-in-time verified: `{str(evidence.point_in_time_verified).lower()}`",
        "- 개인·외국인·기관·기타법인·내외국인 순매수 합계와 기관계 세부 합계를 "
        "원자료 전 행에서 대조합니다.",
        "- 이 증거는 현재 composite score, decision state, action bias를 변경하지 않습니다.",
        "",
        "| 종목 | 구간 | 가격 | 외국인 | 기관 | 외국인+기관 | 거래량 대비 | 상태 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in evidence.windows:
        state = row.descriptive_state if evidence.evidence_verified else "unverified"
        lines.append(
            f"| {row.ticker} | {row.window}d | {_format_pct(row.price_return_pct)} | "
            f"{row.foreign_net_buy_shares} | {row.institution_net_buy_shares} | "
            f"{row.foreign_institution_net_buy_shares} | "
            f"{_format_ratio(row.foreign_institution_volume_ratio)} | {state} |"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "EXPECTED_TICKERS",
    "FlowWindowSummary",
    "InvestorFlowEvidence",
    "SOURCE_SCOPE",
    "TickerDiagnostics",
    "append_investor_flow_report",
    "attach_investor_flow_to_records",
    "attach_investor_flow_to_scorecards",
    "load_investor_flow_evidence",
]
