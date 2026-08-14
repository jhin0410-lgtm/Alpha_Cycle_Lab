"""Certified future catalyst horizon evidence.

Recent disclosures and future catalysts are deliberately separated. A disclosure
that already happened may explain the current thesis but cannot be relabeled as a
future 1/3/6/12-month event. Future catalyst timing is published only when an
official or otherwise source-bounded event date/window is supplied.
"""

from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date


_ALLOWED_TIMING_STATUS = frozenset({"certified_date", "certified_window", "uncertified"})
_ALLOWED_PRICING_STATUS = frozenset({"unknown", "expected", "partially_priced", "surprise_candidate"})
_ALLOWED_SURPRISE = frozenset({"unknown", "low", "medium", "high"})
_ALLOWED_PREREQUISITE = frozenset({"satisfied", "pending", "failed", "unknown"})
_ALLOWED_SOURCE_ROLES = frozenset(
    {"issuer_ir", "customer_ir", "government", "exchange", "contract_disclosure", "regulator"}
)


def _add_calendar_months(value: date, months: int) -> date:
    if months < 0:
        raise ValueError("Catalyst horizon month offset cannot be negative")
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class CatalystEvent:
    event_id: str
    ticker: str
    sector_id: str
    title: str
    description: str
    source_role: str
    source_url: str
    source_published_date: date
    evaluation_date: date
    event_date: date | None
    window_start: date | None
    window_end: date | None
    timing_status: str
    prerequisite_status: str
    prerequisite: str | None
    market_pricing_status: str
    surprise_potential: str
    binary_event: bool
    thesis_invalidation_if_failed: str | None
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.event_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.event_id
        ):
            raise ValueError("Catalyst event_id must be SHA-256")
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Catalyst ticker must be six digits")
        if not self.sector_id.strip() or not self.title.strip() or not self.description.strip():
            raise ValueError("Catalyst sector/title/description cannot be blank")
        if self.source_role not in _ALLOWED_SOURCE_ROLES:
            raise ValueError(f"Unsupported catalyst source role: {self.source_role}")
        if not self.source_url.startswith("https://"):
            raise ValueError("Catalyst source_url must use HTTPS")
        if self.source_published_date > self.evaluation_date:
            raise ValueError("Catalyst source cannot be published after evaluation date")
        if self.timing_status not in _ALLOWED_TIMING_STATUS:
            raise ValueError("Catalyst timing_status is invalid")
        if self.prerequisite_status not in _ALLOWED_PREREQUISITE:
            raise ValueError("Catalyst prerequisite_status is invalid")
        if self.market_pricing_status not in _ALLOWED_PRICING_STATUS:
            raise ValueError("Catalyst market_pricing_status is invalid")
        if self.surprise_potential not in _ALLOWED_SURPRISE:
            raise ValueError("Catalyst surprise_potential is invalid")
        if self.timing_status == "certified_date":
            if self.event_date is None or self.window_start is not None or self.window_end is not None:
                raise ValueError("certified_date requires event_date only")
        elif self.timing_status == "certified_window":
            if self.event_date is not None or self.window_start is None or self.window_end is None:
                raise ValueError("certified_window requires start/end only")
            if self.window_start > self.window_end:
                raise ValueError("Catalyst window_start cannot be after window_end")
        else:
            if self.event_date is not None or self.window_start is not None or self.window_end is not None:
                raise ValueError("uncertified catalyst timing cannot publish date/window")
        if self.decision_score_enabled:
            raise ValueError("Catalyst Horizon v1 must remain non-scoring")

    @property
    def horizon_days(self) -> int | None:
        target = self.event_date if self.event_date is not None else self.window_start
        if target is None:
            return None
        return (target - self.evaluation_date).days

    @property
    def horizon_bucket(self) -> str:
        target = self.event_date if self.event_date is not None else self.window_start
        if target is None:
            return "unscheduled"
        if target < self.evaluation_date:
            return "past_not_future"
        if target <= _add_calendar_months(self.evaluation_date, 1):
            return "1m"
        if target <= _add_calendar_months(self.evaluation_date, 3):
            return "3m"
        if target <= _add_calendar_months(self.evaluation_date, 6):
            return "6m"
        if target <= _add_calendar_months(self.evaluation_date, 12):
            return "12m"
        return "beyond_12m"


@dataclass(frozen=True)
class CatalystHorizonEvidence:
    evidence_id: str
    evaluation_date: date
    events: tuple[CatalystEvent, ...]
    decision_score_enabled: bool = False
    forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.evidence_id
        ):
            raise ValueError("Catalyst horizon evidence_id must be SHA-256")
        if not self.events:
            raise ValueError("Catalyst horizon evidence requires events")
        if any(event.evaluation_date != self.evaluation_date for event in self.events):
            raise ValueError("Catalyst events must share evaluation date")
        if self.decision_score_enabled or self.forecast_enabled:
            raise ValueError("Catalyst horizon evidence must remain non-scoring/non-forecast")


def _event_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def build_catalyst_event(raw: dict[str, object], *, evaluation_date: date) -> CatalystEvent:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    timing_status = str(raw.get("timing_status", "uncertified")).strip()
    event_date_raw = str(raw.get("event_date", "")).strip()
    start_raw = str(raw.get("window_start", "")).strip()
    end_raw = str(raw.get("window_end", "")).strip()
    event_date = date.fromisoformat(event_date_raw) if event_date_raw else None
    window_start = date.fromisoformat(start_raw) if start_raw else None
    window_end = date.fromisoformat(end_raw) if end_raw else None
    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    prerequisite = str(raw.get("prerequisite", "")).strip() or None
    invalidation = str(raw.get("thesis_invalidation_if_failed", "")).strip() or None
    payload: dict[str, object] = {
        "ticker": ticker,
        "sector_id": str(raw.get("sector_id", "")).strip(),
        "title": str(raw.get("title", "")).strip(),
        "description": str(raw.get("description", "")).strip(),
        "source_role": str(raw.get("source_role", "")).strip(),
        "source_url": str(raw.get("source_url", "")).strip(),
        "source_published_date": published.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "event_date": event_date.isoformat() if event_date else None,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "timing_status": timing_status,
        "prerequisite_status": str(raw.get("prerequisite_status", "unknown")).strip(),
        "prerequisite": prerequisite,
        "market_pricing_status": str(raw.get("market_pricing_status", "unknown")).strip(),
        "surprise_potential": str(raw.get("surprise_potential", "unknown")).strip(),
        "binary_event": bool(raw.get("binary_event", False)),
        "thesis_invalidation_if_failed": invalidation,
        "decision_score_enabled": False,
    }
    return CatalystEvent(
        event_id=_event_id(payload),
        ticker=ticker,
        sector_id=str(payload["sector_id"]),
        title=str(payload["title"]),
        description=str(payload["description"]),
        source_role=str(payload["source_role"]),
        source_url=str(payload["source_url"]),
        source_published_date=published,
        evaluation_date=evaluation_date,
        event_date=event_date,
        window_start=window_start,
        window_end=window_end,
        timing_status=timing_status,
        prerequisite_status=str(payload["prerequisite_status"]),
        prerequisite=prerequisite,
        market_pricing_status=str(payload["market_pricing_status"]),
        surprise_potential=str(payload["surprise_potential"]),
        binary_event=bool(payload["binary_event"]),
        thesis_invalidation_if_failed=invalidation,
        decision_score_enabled=False,
    )


def build_catalyst_horizon_evidence(
    raw_events: list[dict[str, object]],
    *,
    evaluation_date: date,
) -> CatalystHorizonEvidence:
    events = tuple(build_catalyst_event(raw, evaluation_date=evaluation_date) for raw in raw_events)
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("Catalyst horizon contains duplicate events")
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "events": [
            {
                "event_id": event.event_id,
                "ticker": event.ticker,
                "sector_id": event.sector_id,
                "timing_status": event.timing_status,
                "horizon_bucket": event.horizon_bucket,
                "prerequisite_status": event.prerequisite_status,
                "market_pricing_status": event.market_pricing_status,
                "surprise_potential": event.surprise_potential,
                "binary_event": event.binary_event,
            }
            for event in events
        ],
        "decision_score_enabled": False,
        "forecast_enabled": False,
    }
    return CatalystHorizonEvidence(
        evidence_id=_event_id(payload),
        evaluation_date=evaluation_date,
        events=events,
    )


__all__ = [
    "CatalystEvent",
    "CatalystHorizonEvidence",
    "build_catalyst_event",
    "build_catalyst_horizon_evidence",
]
