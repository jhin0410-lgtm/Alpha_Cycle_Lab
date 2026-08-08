"""Bind validated Kiwoom investor-flow artifacts to the current market session.

The raw OPT10059 artifact is first validated against its own request/capture date.
Decision-time freshness is then determined from the primary market context's latest
observed session for each ticker, rather than by requiring the artifact request date
to equal the decision calendar date. This preserves weekend/holiday carry-forward
while failing closed as soon as the market advances to a newer session.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.investor_flow_evidence import (
    InvestorFlowEvidence,
    load_investor_flow_evidence,
)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, object], payload)


def _reference_date_from_pointer(pointer_path: str | Path) -> date:
    pointer = _read_json(Path(pointer_path))
    manifest_path = Path(str(pointer.get("manifest_path", "")))
    if not manifest_path.is_file():
        raise FileNotFoundError(f"investor-flow manifest not found: {manifest_path}")
    manifest = _read_json(manifest_path)
    raw = str(manifest.get("reference_date", ""))
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("investor-flow manifest reference_date must use YYYYMMDD") from exc


def _evidence_reference_date(evidence: InvestorFlowEvidence) -> date | None:
    try:
        return datetime.strptime(evidence.reference_date, "%Y%m%d").date()
    except ValueError:
        return None


def _evidence_captured_date(evidence: InvestorFlowEvidence) -> date | None:
    try:
        return date.fromisoformat(evidence.captured_date)
    except ValueError:
        return None


def extract_market_session_dates(market_context: pd.DataFrame) -> dict[str, date]:
    """Return ticker -> latest observed Korean-market session date.

    ``build_market_context`` stores timezone-aware UTC timestamps. Converting them
    back to Asia/Seoul avoids shifting a Korean daily-bar session to the prior UTC
    calendar date.
    """

    required = {"ticker", "last_timestamp"}
    missing = sorted(required - set(market_context.columns))
    if missing:
        raise ValueError("market context missing session columns: " + ",".join(missing))
    normalized = market_context.loc[:, ["ticker", "last_timestamp"]].copy()
    normalized["ticker"] = normalized["ticker"].astype("string").str.zfill(6)
    if normalized["ticker"].duplicated().any():
        raise ValueError("market context contains duplicate tickers")

    sessions: dict[str, date] = {}
    for raw in normalized.to_dict(orient="records"):
        ticker = str(raw["ticker"])
        value = raw["last_timestamp"]
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid market last_timestamp for {ticker}") from exc
        if pd.isna(timestamp):
            raise ValueError(f"missing market last_timestamp for {ticker}")
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        local = timestamp.tz_convert("Asia/Seoul")
        sessions[ticker] = local.date()
    return sessions


def _mark_unverified(
    evidence: InvestorFlowEvidence,
    *,
    evaluation_date: date,
    reason: str,
) -> InvestorFlowEvidence:
    return replace(
        evidence,
        status="unverified",
        reason=reason,
        point_in_time_verified=False,
        evidence_verified=False,
        evaluation_date=evaluation_date.isoformat(),
    )


def align_investor_flow_to_market_session(
    evidence: InvestorFlowEvidence,
    *,
    evaluation_date: date,
    market_context: pd.DataFrame,
) -> InvestorFlowEvidence:
    """Apply decision-time market-session freshness to a capture-validated artifact."""

    if not evidence.evidence_verified:
        return replace(evidence, evaluation_date=evaluation_date.isoformat())

    reference_date = _evidence_reference_date(evidence)
    if reference_date is None:
        return _mark_unverified(
            evidence,
            evaluation_date=evaluation_date,
            reason="invalid_reference_date",
        )
    if reference_date > evaluation_date:
        return _mark_unverified(
            evidence,
            evaluation_date=evaluation_date,
            reason="reference_date_after_evaluation",
        )

    captured_date = _evidence_captured_date(evidence)
    if captured_date is None:
        return _mark_unverified(
            evidence,
            evaluation_date=evaluation_date,
            reason="invalid_captured_date",
        )
    if captured_date > evaluation_date:
        return _mark_unverified(
            evidence,
            evaluation_date=evaluation_date,
            reason="captured_date_after_evaluation",
        )

    market_sessions = extract_market_session_dates(market_context)
    flow_tickers = sorted(
        {
            row.ticker
            for row in evidence.windows
            if row.window == 20 and row.observations >= 20
        }
    )
    if not flow_tickers:
        return _mark_unverified(
            evidence,
            evaluation_date=evaluation_date,
            reason="flow_session_unavailable",
        )

    for ticker in flow_tickers:
        market_session = market_sessions.get(ticker)
        if market_session is None:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"market_session_unavailable:{ticker}",
            )
        if market_session > evaluation_date:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"market_session_after_evaluation:{ticker}",
            )
        window = evidence.window(ticker, 20)
        if window is None or not window.latest_date:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"flow_session_unavailable:{ticker}",
            )
        try:
            flow_session = datetime.strptime(window.latest_date, "%Y%m%d").date()
        except ValueError:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"invalid_flow_session:{ticker}",
            )
        if flow_session > reference_date:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"flow_session_after_reference:{ticker}",
            )
        if flow_session > evaluation_date:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=f"flow_session_after_evaluation:{ticker}",
            )
        if flow_session != market_session:
            return _mark_unverified(
                evidence,
                evaluation_date=evaluation_date,
                reason=(
                    f"market_session_mismatch:{ticker}:"
                    f"flow={flow_session.isoformat()}:market={market_session.isoformat()}"
                ),
            )

    return replace(
        evidence,
        status="verified",
        reason="verified_live_market_session_evidence",
        point_in_time_verified=True,
        evidence_verified=True,
        evaluation_date=evaluation_date.isoformat(),
    )


def load_market_session_aligned_investor_flow_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    market_context: pd.DataFrame,
) -> InvestorFlowEvidence:
    """Validate an immutable flow artifact at capture, then bind it to market session."""

    reference_date = _reference_date_from_pointer(pointer_path)
    capture_evidence = load_investor_flow_evidence(
        pointer_path,
        evaluation_date=reference_date,
    )
    return align_investor_flow_to_market_session(
        capture_evidence,
        evaluation_date=evaluation_date,
        market_context=market_context,
    )


__all__ = [
    "align_investor_flow_to_market_session",
    "extract_market_session_dates",
    "load_market_session_aligned_investor_flow_evidence",
]
