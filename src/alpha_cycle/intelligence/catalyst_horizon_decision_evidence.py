"""Decision-facing loader and readiness summary for Catalyst Horizon v1."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.catalyst_horizon import (
    CatalystHorizonEvidence,
    build_catalyst_horizon_evidence,
)

DEFAULT_CATALYST_HORIZON_POINTER = Path(
    "data/private/live-research/catalyst-horizon-evidence/"
    "latest_catalyst_horizon_evidence.json"
)
_REQUIRED_FALSE_FLAGS = (
    "source_bytes_archived",
    "historical_snapshot_certified",
    "decision_score_enabled",
    "forecast_enabled",
    "account_api_enabled",
    "holdings_api_enabled",
    "balance_api_enabled",
    "order_api_enabled",
)


@dataclass(frozen=True)
class CatalystHorizonDecisionEvidence:
    evidence: CatalystHorizonEvidence
    summary: pd.DataFrame
    decision_score_enabled: bool = False
    forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if self.summary.empty:
            raise ValueError("Catalyst horizon decision summary cannot be empty")
        if self.decision_score_enabled or self.forecast_enabled:
            raise ValueError("Catalyst horizon decision evidence must remain non-scoring")


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _require_false(payload: Mapping[str, object]) -> None:
    for key in _REQUIRED_FALSE_FLAGS:
        if payload.get(key) is not False:
            raise ValueError(f"Catalyst horizon requires {key}=false")


def _raw_events(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Catalyst horizon events not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Catalyst horizon events are invalid JSON: {path}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("Catalyst horizon events artifact must be a non-empty array")
    rows: list[dict[str, object]] = []
    for value in payload:
        if not isinstance(value, dict):
            raise ValueError("Catalyst horizon event row must be an object")
        raw = cast(dict[object, object], value)
        rows.append(
            {
                "ticker": raw.get("ticker"),
                "sector_id": raw.get("sector_id"),
                "title": raw.get("title"),
                "description": raw.get("description"),
                "source_role": raw.get("source_role"),
                "source_url": raw.get("source_url"),
                "source_published_date": raw.get("source_published_date"),
                "event_date": raw.get("event_date"),
                "window_start": raw.get("window_start"),
                "window_end": raw.get("window_end"),
                "timing_status": raw.get("timing_status"),
                "prerequisite_status": raw.get("prerequisite_status"),
                "prerequisite": raw.get("prerequisite"),
                "market_pricing_status": raw.get("market_pricing_status"),
                "surprise_potential": raw.get("surprise_potential"),
                "binary_event": raw.get("binary_event", False),
                "thesis_invalidation_if_failed": raw.get("thesis_invalidation_if_failed"),
            }
        )
    return rows


def _summary(evidence: CatalystHorizonEvidence) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    tickers = sorted({event.ticker for event in evidence.events})
    for ticker in tickers:
        events = [event for event in evidence.events if event.ticker == ticker]
        future = [
            event
            for event in events
            if event.horizon_bucket in {"1m", "3m", "6m", "12m", "beyond_12m"}
        ]
        certified = [
            event
            for event in future
            if event.timing_status in {"certified_date", "certified_window"}
        ]
        rows.append(
            {
                "ticker": ticker,
                "catalyst_horizon_evidence_id": evidence.evidence_id,
                "catalyst_event_count": len(events),
                "future_certified_event_count": len(certified),
                "catalyst_1m_count": sum(event.horizon_bucket == "1m" for event in certified),
                "catalyst_3m_count": sum(event.horizon_bucket == "3m" for event in certified),
                "catalyst_6m_count": sum(event.horizon_bucket == "6m" for event in certified),
                "catalyst_12m_count": sum(event.horizon_bucket == "12m" for event in certified),
                "binary_event_count": sum(event.binary_event for event in certified),
                "pending_prerequisite_count": sum(
                    event.prerequisite_status == "pending" for event in certified
                ),
                "surprise_candidate_count": sum(
                    event.market_pricing_status == "surprise_candidate" for event in certified
                ),
                "catalyst_horizon_status": (
                    "future_timing_evidence_available" if certified else "no_certified_future_event"
                ),
                "decision_score_enabled": False,
                "forecast_enabled": False,
            }
        )
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def load_catalyst_horizon_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> CatalystHorizonDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Catalyst horizon pointer")
    if str(pointer.get("status", "")) != "catalyst_horizon_evidence_captured":
        raise ValueError("Catalyst horizon pointer status is invalid")
    _require_false(pointer)
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Catalyst horizon evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    evidence_id = str(pointer.get("evidence_id", "")).strip()
    if len(evidence_id) != 64:
        raise ValueError("Catalyst horizon pointer evidence_id is invalid")
    manifest_path = Path(str(pointer.get("manifest_path", "")).strip())
    events_path = Path(str(pointer.get("events_path", "")).strip())
    manifest = _json_object(manifest_path, "Catalyst horizon manifest")
    if str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("Catalyst horizon pointer/manifest evidence mismatch")
    _require_false(manifest)
    evidence = build_catalyst_horizon_evidence(
        _raw_events(events_path),
        evaluation_date=evaluation_date,
    )
    if evidence.evidence_id != evidence_id:
        raise ValueError("Catalyst horizon artifact hash does not reproduce evidence_id")
    return CatalystHorizonDecisionEvidence(
        evidence=evidence,
        summary=_summary(evidence),
    )


def append_catalyst_horizon_report(
    report: str,
    evidence: CatalystHorizonDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Catalyst Horizon v1 (미래일정·비점수)",
        "",
        f"- evidence: `{evidence.evidence.evidence_id[:12]}` / evaluation `{evidence.evidence.evaluation_date.isoformat()}`",
        "- 최근 공시와 미래 촉매를 분리하며, timing이 인증된 date/window만 1/3/6/12개월 horizon에 포함합니다.",
        "- market pricing/surprise/binary/prerequisite는 사건의 성격을 설명할 뿐 자동 매수·매도 점수가 아닙니다.",
        "- source bytes가 archive되지 않은 artifact는 historical snapshot certification을 주장하지 않습니다.",
        "",
        "| 종목 | 미래 인증 event | 1m | 3m | 6m | 12m | binary | pending prerequisite | surprise candidate | 상태 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for raw in evidence.summary.to_dict(orient="records"):
        lines.append(
            f"| {raw['ticker']} | {raw['future_certified_event_count']} | "
            f"{raw['catalyst_1m_count']} | {raw['catalyst_3m_count']} | "
            f"{raw['catalyst_6m_count']} | {raw['catalyst_12m_count']} | "
            f"{raw['binary_event_count']} | {raw['pending_prerequisite_count']} | "
            f"{raw['surprise_candidate_count']} | {raw['catalyst_horizon_status']} |"
        )
    lines.extend(["", "### Future events", ""])
    for event in sorted(
        evidence.evidence.events,
        key=lambda item: (
            item.ticker,
            item.horizon_days if item.horizon_days is not None else 10**9,
            item.title,
        ),
    ):
        lines.append(
            f"- `{event.ticker}` / `{event.horizon_bucket}` / `{event.timing_status}` / "
            f"pricing `{event.market_pricing_status}` / surprise `{event.surprise_potential}` / "
            f"prerequisite `{event.prerequisite_status}`: {event.title}"
        )
        if event.thesis_invalidation_if_failed:
            lines.append(f"  - invalidation if failed: {event.thesis_invalidation_if_failed}")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_CATALYST_HORIZON_POINTER",
    "CatalystHorizonDecisionEvidence",
    "append_catalyst_horizon_report",
    "load_catalyst_horizon_decision_evidence",
]
