"""Plan current official semiconductor IR collection without stale fallbacks.

The refresh selects at most one latest observable registered document per issuer.
An issuer with no verified document remains an explicit research gap.  If the latest
registered document fails collection, callers must report that failure rather than
silently falling back to an older document and presenting it as current evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    OfficialIrDocumentSpec,
    load_official_ir_document_registry,
)


@dataclass(frozen=True)
class IssuerIrRefreshPlan:
    ticker: str
    issuer_name: str
    selected_document_id: str | None
    selected_period_end: date | None
    status: str
    reason: str | None

    def __post_init__(self) -> None:
        allowed = {"registered_observable_document", "unresolved_no_registered_document"}
        if self.status not in allowed:
            raise ValueError("Official IR issuer refresh status is invalid")
        if self.status == "registered_observable_document":
            if self.selected_document_id is None or self.selected_period_end is None:
                raise ValueError("Observable IR refresh plan requires a selected document")
        elif self.selected_document_id is not None or self.selected_period_end is not None:
            raise ValueError("Unresolved IR refresh plan cannot select a document")


@dataclass(frozen=True)
class OfficialIrRefreshPlan:
    evaluation_date: date
    issuers: tuple[IssuerIrRefreshPlan, ...]

    def __post_init__(self) -> None:
        if not self.issuers:
            raise ValueError("Official IR refresh plan requires issuer entries")
        tickers = [item.ticker for item in self.issuers]
        if len(tickers) != len(set(tickers)):
            raise ValueError("Official IR refresh plan contains duplicate issuers")

    @property
    def selected_document_ids(self) -> tuple[str, ...]:
        return tuple(
            item.selected_document_id
            for item in self.issuers
            if item.selected_document_id is not None
        )


def _issuer_metadata(path: Path) -> dict[str, tuple[str, str | None]]:
    with path.open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("Official IR registry must contain issuers")
    result: dict[str, tuple[str, str | None]] = {}
    for raw_ticker, raw_value in cast(dict[object, object], payload["issuers"]).items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_value, dict):
            raise ValueError(f"Official IR issuer entry must be an object: {ticker}")
        raw = cast(dict[object, object], raw_value)
        issuer_name = str(raw.get("issuer_name", "")).strip()
        reason = str(raw.get("unresolved_latest_official_document_reason", "")).strip() or None
        if not issuer_name:
            raise ValueError(f"Official IR issuer name is blank: {ticker}")
        result[ticker] = (issuer_name, reason)
    if not result:
        raise ValueError("Official IR refresh registry has no issuers")
    return result


def build_official_ir_refresh_plan(
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_IR_DOCUMENT_REGISTRY,
) -> OfficialIrRefreshPlan:
    path = Path(registry_path)
    specs = load_official_ir_document_registry(path)
    metadata = _issuer_metadata(path)
    rows: list[IssuerIrRefreshPlan] = []
    for ticker, (issuer_name, unresolved_reason) in sorted(metadata.items()):
        observable = [
            spec
            for spec in specs.values()
            if spec.ticker == ticker
            and spec.period_end <= evaluation_date
            and spec.source_published_date <= evaluation_date
        ]
        if observable:
            selected: OfficialIrDocumentSpec = max(
                observable,
                key=lambda item: (
                    item.period_end,
                    item.source_published_date,
                    item.document_id,
                ),
            )
            rows.append(
                IssuerIrRefreshPlan(
                    ticker=ticker,
                    issuer_name=issuer_name,
                    selected_document_id=selected.document_id,
                    selected_period_end=selected.period_end,
                    status="registered_observable_document",
                    reason=None,
                )
            )
            continue
        reason = unresolved_reason or (
            "No registered official IR document is observable by the evaluation date."
        )
        rows.append(
            IssuerIrRefreshPlan(
                ticker=ticker,
                issuer_name=issuer_name,
                selected_document_id=None,
                selected_period_end=None,
                status="unresolved_no_registered_document",
                reason=reason,
            )
        )
    return OfficialIrRefreshPlan(evaluation_date=evaluation_date, issuers=tuple(rows))


__all__ = [
    "IssuerIrRefreshPlan",
    "OfficialIrRefreshPlan",
    "build_official_ir_refresh_plan",
]
