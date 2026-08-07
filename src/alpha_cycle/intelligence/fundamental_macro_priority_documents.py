"""Priority-aware bounded OpenDART document collection for live research.

This module preserves the existing bounded collection contract while reserving room
for both core operating evidence and recent correction filings. After selected
correction bodies are collected, it performs a second bounded pass for the exact
parent filing date stated in the correction body.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence.decision_features import classify_disclosures
from alpha_cycle.intelligence.disclosure_correction_parent import (
    correction_target_submission_date,
)
from alpha_cycle.intelligence.disclosure_provenance import normalize_disclosure_tables
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroCollector as BaseFundamentalMacroCollector,
)
from alpha_cycle.intelligence.fundamental_macro import FundamentalMacroSnapshot
from alpha_cycle.intelligence.fundamental_macro_documents import (
    DEFAULT_MAX_DOCUMENTS_PER_TICKER,
    DEFAULT_MAX_SUPPORT_DOCUMENTS_PER_TICKER,
    MAX_CORRECTION_ANCESTORS_PER_SELECTED,
    _correction_support_plan,
    _is_periodic_report,
    _row_record,
)
from alpha_cycle.providers.ecos import EcosReadOnlyClient, EcosSeriesSpec
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import OpenDartDisclosureDocumentClient

DOCUMENT_EVIDENCE_SCHEMA_VERSION = 4
DEFAULT_CORE_DOCUMENT_RESERVE = 6
DEFAULT_CORRECTION_DOCUMENT_RESERVE = 4
PRIORITY_RESERVE_MIN_CAPACITY = 6
DEFAULT_BODY_TARGET_SUPPORT_RESERVE = 8
CORE_CATEGORIES = frozenset(
    {
        "operational_risk",
        "contract_order",
        "capex_investment",
        "earnings",
    }
)


def _support_reserve(max_support_documents_per_ticker: int) -> int:
    if max_support_documents_per_ticker <= 2:
        return 0
    return min(
        DEFAULT_BODY_TARGET_SUPPORT_RESERVE,
        max_support_documents_per_ticker // 3,
    )


def _priority_select_receipts(
    group: pd.DataFrame,
    *,
    capacity: int,
) -> dict[str, str]:
    """Return selected receipt numbers and their deterministic selection reason."""

    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if group.empty:
        return {}

    eligible = group.loc[~group["report_name"].map(_is_periodic_report)].copy()
    if eligible.empty:
        return {}

    material_order = eligible.sort_values(
        ["material_score", "receipt_date", "rcept_no"],
        ascending=[False, False, False],
        kind="stable",
    )
    if capacity < PRIORITY_RESERVE_MIN_CAPACITY:
        return {
            str(raw["rcept_no"]): "bounded_material_event_selection"
            for raw in material_order.head(capacity).to_dict(orient="records")
        }

    correction_target = min(
        DEFAULT_CORRECTION_DOCUMENT_RESERVE,
        max(1, capacity // 3),
    )
    core_target = min(
        DEFAULT_CORE_DOCUMENT_RESERVE,
        max(1, capacity - correction_target),
    )

    selected: dict[str, str] = {}
    core = material_order.loc[material_order["category"].isin(CORE_CATEGORIES)]
    for raw in core.head(core_target).to_dict(orient="records"):
        selected[str(raw["rcept_no"])] = "bounded_core_event_reserve"

    selected_corrections = sum(
        1
        for raw in eligible.to_dict(orient="records")
        if str(raw["rcept_no"]) in selected and bool(raw.get("is_correction", False))
    )
    corrections = eligible.loc[eligible["is_correction"].astype(bool)].sort_values(
        ["receipt_date", "material_score", "rcept_no"],
        ascending=[False, False, False],
        kind="stable",
    )
    for raw in corrections.to_dict(orient="records"):
        if len(selected) >= capacity or selected_corrections >= correction_target:
            break
        receipt = str(raw["rcept_no"])
        if receipt in selected:
            continue
        selected[receipt] = "bounded_recent_correction_reserve"
        selected_corrections += 1

    for raw in material_order.to_dict(orient="records"):
        if len(selected) >= capacity:
            break
        receipt = str(raw["rcept_no"])
        selected.setdefault(receipt, "bounded_material_event_fill")

    return selected


def _priority_selection_plan(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    max_documents_per_ticker: int,
    max_support_documents_per_ticker: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, dict[str, object]],
    tuple[str, ...],
]:
    if max_documents_per_ticker <= 0:
        raise ValueError("max_documents_per_ticker must be positive")
    if max_support_documents_per_ticker <= 0:
        raise ValueError("max_support_documents_per_ticker must be positive")

    events, catalysts, summary = classify_disclosures(
        disclosures,
        evaluation_date=evaluation_date,
        recent_days=365,
    )
    normalized_events, normalized, _, _ = normalize_disclosure_tables(
        events,
        catalysts,
        summary,
    )
    if normalized.empty:
        return (
            normalized.copy(),
            normalized_events.iloc[0:0].copy(),
            normalized_events,
            {},
            (),
        )

    ordered = normalized.sort_values(
        ["ticker", "material_score", "receipt_date", "rcept_no"],
        ascending=[True, False, False, False],
        kind="stable",
    ).reset_index(drop=True)
    ledger: dict[str, dict[str, object]] = {}
    selected_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for ticker, group in ordered.groupby("ticker", sort=True):
        reasons = _priority_select_receipts(
            group,
            capacity=max_documents_per_ticker,
        )
        eligible_total = int((~group["report_name"].map(_is_periodic_report)).sum())
        for raw_value in group.to_dict(orient="records"):
            raw = {str(key): value for key, value in raw_value.items()}
            record = _row_record(raw)
            receipt = str(record["rcept_no"])
            if not receipt or receipt in ledger:
                raise ValueError(
                    "Disclosure document selection requires unique receipt numbers"
                )
            record["role"] = "primary_catalyst"
            if _is_periodic_report(record["report_name"]):
                record.update(
                    {
                        "status": "excluded_periodic",
                        "selection_reason": "periodic_report_financial_evidence_path",
                    }
                )
            elif receipt in reasons:
                record.update(
                    {
                        "status": "selected_pending",
                        "selection_reason": reasons[receipt],
                    }
                )
                selected_rows.append(raw)
            else:
                record.update(
                    {
                        "status": "excluded_capacity",
                        "selection_reason": "bounded_document_collection_capacity",
                    }
                )
            ledger[receipt] = record
        if eligible_total > max_documents_per_ticker:
            warnings.append(
                "disclosure_document_selection_truncated:"
                f"{str(ticker).zfill(6)}:{max_documents_per_ticker}/{eligible_total}"
            )

    selected = pd.DataFrame(selected_rows)
    if selected.empty:
        selected = normalized.iloc[0:0].copy()
    else:
        selected = selected.reindex(columns=normalized.columns)

    body_target_reserve = _support_reserve(max_support_documents_per_ticker)
    heuristic_support_budget = max_support_documents_per_ticker - body_target_reserve
    support, supporters, support_warnings = _correction_support_plan(
        selected,
        normalized_events,
        max_support_documents_per_ticker=max(1, heuristic_support_budget),
    )
    warnings.extend(support_warnings)
    for raw_value in support.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        record = _row_record(raw)
        receipt = str(record["rcept_no"])
        if receipt in ledger:
            existing = ledger[receipt]
            if existing.get("status") != "selected_pending":
                raise ValueError(
                    "Correction support collides with a non-selected primary catalyst"
                )
            existing["also_correction_support"] = True
            existing["supports_selected_receipts"] = supporters.get(receipt, [])
            continue
        record.update(
            {
                "role": "correction_parent_support",
                "status": "selected_support_pending",
                "selection_reason": "correction_lineage_support",
                "supports_selected_receipts": supporters.get(receipt, []),
            }
        )
        ledger[receipt] = record

    return (
        selected.reset_index(drop=True),
        support.reset_index(drop=True),
        normalized_events.reset_index(drop=True),
        ledger,
        tuple(dict.fromkeys(warnings)),
    )


def _candidate_rows_for_body_target(
    events: pd.DataFrame,
    *,
    ticker: str,
    family: str,
    target_date: date,
    current_receipt: str,
) -> pd.DataFrame:
    if events.empty:
        return events.iloc[0:0].copy()
    dates = pd.to_datetime(events["receipt_date"], errors="raise").dt.date
    mask = (
        events["ticker"].astype(str).str.zfill(6).eq(ticker)
        & events["correction_family_key"].astype(str).eq(family)
        & dates.eq(target_date)
        & ~events["rcept_no"].astype(str).eq(current_receipt)
    )
    return events.loc[mask].copy()


def _body_target_support_plan(
    selected: pd.DataFrame,
    events: pd.DataFrame,
    documents: dict[str, dict[str, object]],
    *,
    max_support_documents_per_ticker: int,
    existing_support_receipts: set[str],
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Select exact correction parents from the target date stated in body text."""

    warnings: list[str] = []
    pending_rows: list[dict[str, object]] = []
    used_by_ticker: Counter[str] = Counter()
    for receipt in existing_support_receipts:
        record = documents.get(receipt)
        if record is not None:
            used_by_ticker[str(record.get("ticker", "")).zfill(6)] += 1

    corrections = selected.loc[selected["is_correction"].astype(bool)].sort_values(
        ["receipt_date", "rcept_no"],
        ascending=[False, False],
        kind="stable",
    )
    for raw_value in corrections.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        current_receipt = str(raw.get("rcept_no", "")).strip()
        current = documents.get(current_receipt)
        if current is None or current.get("status") != "collected":
            continue
        ticker = str(raw.get("ticker", "")).strip().zfill(6)
        family = str(raw.get("correction_family_key", "")).strip()
        target_date = correction_target_submission_date(current.get("text", ""))
        if target_date is None:
            warnings.append(
                "disclosure_body_target_support_date_missing:"
                f"{ticker}:{current_receipt}"
            )
            continue
        candidates = _candidate_rows_for_body_target(
            events,
            ticker=ticker,
            family=family,
            target_date=target_date,
            current_receipt=current_receipt,
        )
        receipts = sorted(set(candidates["rcept_no"].astype(str)))
        if not receipts:
            warnings.append(
                "disclosure_body_target_support_not_found:"
                f"{ticker}:{current_receipt}:{target_date.isoformat()}"
            )
            continue
        if len(receipts) != 1:
            warnings.append(
                "disclosure_body_target_support_ambiguous:"
                f"{ticker}:{current_receipt}:{target_date.isoformat()}:{len(receipts)}"
            )
            continue

        parent_receipt = receipts[0]
        existing = documents.get(parent_receipt)
        if existing is not None and existing.get("status") == "collected":
            raw_supporters = existing.get("supports_body_target_receipts", [])
            supporters = (
                [str(item) for item in raw_supporters]
                if isinstance(raw_supporters, list)
                else []
            )
            if current_receipt not in supporters:
                supporters.append(current_receipt)
            existing["supports_body_target_receipts"] = supporters
            existing["also_body_target_support"] = True
            continue
        if used_by_ticker[ticker] >= max_support_documents_per_ticker:
            warnings.append(
                "disclosure_body_target_support_capacity_truncated:"
                f"{ticker}:{current_receipt}:{parent_receipt}"
            )
            continue

        candidate = candidates.iloc[0].to_dict()
        if existing is None:
            record = _row_record({str(key): value for key, value in candidate.items()})
            record.update(
                {
                    "role": "correction_body_target_support",
                    "status": "selected_body_target_support_pending",
                    "selection_reason": "correction_body_target_submission_date",
                    "supports_body_target_receipts": [current_receipt],
                }
            )
            documents[parent_receipt] = record
        elif existing.get("status") == "excluded_capacity":
            existing["primary_selection_status_before_body_target_support"] = (
                "excluded_capacity"
            )
            existing["status"] = "selected_body_target_support_pending"
            existing["selection_reason"] = "correction_body_target_submission_date"
            existing["also_body_target_support"] = True
            existing["supports_body_target_receipts"] = [current_receipt]
        else:
            warnings.append(
                "disclosure_body_target_support_existing_unavailable:"
                f"{ticker}:{current_receipt}:{parent_receipt}:"
                f"{existing.get('status', 'unknown')}"
            )
            continue

        pending_rows.append({str(key): value for key, value in candidate.items()})
        existing_support_receipts.add(parent_receipt)
        used_by_ticker[ticker] += 1

    pending = pd.DataFrame(pending_rows)
    if pending.empty:
        pending = events.iloc[0:0].copy()
    else:
        pending = pending.reindex(columns=events.columns)
    return pending.reset_index(drop=True), tuple(dict.fromkeys(warnings))


class FundamentalMacroCollector(BaseFundamentalMacroCollector):
    """Official-data collector with priority-aware bounded filing-body evidence."""

    def __init__(
        self,
        opendart: OpenDartReadOnlyClient,
        ecos: EcosReadOnlyClient,
        *,
        document_client: OpenDartDisclosureDocumentClient | None = None,
        max_documents_per_ticker: int = DEFAULT_MAX_DOCUMENTS_PER_TICKER,
        max_support_documents_per_ticker: int = DEFAULT_MAX_SUPPORT_DOCUMENTS_PER_TICKER,
    ) -> None:
        super().__init__(opendart, ecos)
        if max_documents_per_ticker <= 0:
            raise ValueError("max_documents_per_ticker must be positive")
        if max_support_documents_per_ticker <= 0:
            raise ValueError("max_support_documents_per_ticker must be positive")
        self.document_client = document_client or OpenDartDisclosureDocumentClient(opendart)
        self.max_documents_per_ticker = max_documents_per_ticker
        self.max_support_documents_per_ticker = max_support_documents_per_ticker

    def _download_frame(
        self,
        frame: pd.DataFrame,
        documents: dict[str, dict[str, object]],
        warnings: list[str],
        *,
        pending_status: str,
        failure_status: str,
        warning_prefix: str,
        captured_at: datetime,
    ) -> datetime:
        latest = captured_at
        for row_value in frame.to_dict(orient="records"):
            row = {str(key): value for key, value in row_value.items()}
            ticker = str(row.get("ticker", "")).strip().zfill(6)
            receipt = str(row.get("rcept_no", "")).strip()
            record = documents.get(receipt)
            if record is None or record.get("status") != pending_status:
                if (
                    pending_status == "selected_support_pending"
                    and record is not None
                    and record.get("status") == "selected_pending"
                    and record.get("also_correction_support") is True
                ):
                    continue
                raise ValueError("Disclosure document selection ledger binding mismatch")
            try:
                evidence = self.document_client.document(receipt)
            except (OSError, TypeError, ValueError) as exc:
                record.update(
                    {
                        "status": failure_status,
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                    }
                )
                warnings.append(f"{warning_prefix}:{ticker}:{receipt}")
            else:
                record.update({"status": "collected", **evidence.as_dict()})
                if evidence.retrieved_at > latest:
                    latest = evidence.retrieved_at
                for item in evidence.warnings:
                    warnings.append(
                        f"disclosure_document_warning:{ticker}:{receipt}:{item}"
                    )
        return latest

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        business_year: int,
        report_code: str,
        fs_div: str,
        disclosure_begin: date,
        disclosure_end: date,
        ecos_specs: tuple[EcosSeriesSpec, ...],
        evaluation_date: date,
        revision_policy: RevisionPolicy,
        market_snapshot: Path | None = None,
    ) -> FundamentalMacroSnapshot:
        base = super().collect(
            symbols,
            business_year=business_year,
            report_code=report_code,
            fs_div=fs_div,
            disclosure_begin=disclosure_begin,
            disclosure_end=disclosure_end,
            ecos_specs=ecos_specs,
            evaluation_date=evaluation_date,
            revision_policy=revision_policy,
            market_snapshot=market_snapshot,
        )
        selected, support, events, documents, selection_warnings = (
            _priority_selection_plan(
                base.disclosures,
                evaluation_date=evaluation_date,
                max_documents_per_ticker=self.max_documents_per_ticker,
                max_support_documents_per_ticker=(
                    self.max_support_documents_per_ticker
                ),
            )
        )

        raw_value = deepcopy(base.raw_opendart)
        if not isinstance(raw_value, dict):
            raise ValueError("OpenDART raw payload must be an object")
        raw = cast(dict[str, object], raw_value)
        warnings = [*base.warnings, *selection_warnings]
        captured_at = base.captured_at

        captured_at = self._download_frame(
            selected,
            documents,
            warnings,
            pending_status="selected_pending",
            failure_status="unavailable",
            warning_prefix="disclosure_document_unavailable",
            captured_at=captured_at,
        )
        captured_at = self._download_frame(
            support,
            documents,
            warnings,
            pending_status="selected_support_pending",
            failure_status="support_unavailable",
            warning_prefix="disclosure_correction_support_unavailable",
            captured_at=captured_at,
        )

        support_receipts = (
            set(support["rcept_no"].astype(str)) if not support.empty else set()
        )
        body_target_support, body_target_warnings = _body_target_support_plan(
            selected,
            events,
            documents,
            max_support_documents_per_ticker=self.max_support_documents_per_ticker,
            existing_support_receipts=support_receipts,
        )
        warnings.extend(body_target_warnings)
        captured_at = self._download_frame(
            body_target_support,
            documents,
            warnings,
            pending_status="selected_body_target_support_pending",
            failure_status="body_target_support_unavailable",
            warning_prefix="disclosure_body_target_support_unavailable",
            captured_at=captured_at,
        )

        pending_statuses = {
            "selected_pending",
            "selected_support_pending",
            "selected_body_target_support_pending",
        }
        if any(record.get("status") in pending_statuses for record in documents.values()):
            raise ValueError("Disclosure document selection contains unresolved pending records")

        selected_counts = (
            {
                str(ticker).zfill(6): int(count)
                for ticker, count in selected.groupby("ticker", sort=True).size().items()
            }
            if not selected.empty
            else {}
        )
        all_support = pd.concat(
            [support, body_target_support],
            ignore_index=True,
        ).drop_duplicates(subset=["rcept_no"], keep="first")
        support_counts = (
            {
                str(ticker).zfill(6): int(count)
                for ticker, count in all_support.groupby("ticker", sort=True).size().items()
            }
            if not all_support.empty
            else {}
        )
        status_counts = dict(
            Counter(
                str(record.get("status", "unknown"))
                for record in documents.values()
            )
        )
        raw["_disclosure_document_evidence"] = {
            "schema_version": DOCUMENT_EVIDENCE_SCHEMA_VERSION,
            "provider": "opendart",
            "endpoint": "/api/document.xml",
            "selection_policy": {
                "recent_days": 365,
                "max_documents_per_ticker": self.max_documents_per_ticker,
                "periodic_reports_excluded": True,
                "latest_correction_chain_only": True,
                "high_or_critical_materiality_only": True,
                "capacity_exclusions_are_noncertified_backlog": True,
                "priority_aware_primary_selection_enabled": True,
                "core_categories": sorted(CORE_CATEGORIES),
                "core_document_reserve": DEFAULT_CORE_DOCUMENT_RESERVE,
                "correction_document_reserve": DEFAULT_CORRECTION_DOCUMENT_RESERVE,
                "priority_reserve_min_capacity": PRIORITY_RESERVE_MIN_CAPACITY,
                "correction_parent_support_enabled": True,
                "max_correction_ancestors_per_selected": (
                    MAX_CORRECTION_ANCESTORS_PER_SELECTED
                ),
                "max_support_documents_per_ticker": (
                    self.max_support_documents_per_ticker
                ),
                "body_target_support_second_pass_enabled": True,
                "body_target_support_reserve": _support_reserve(
                    self.max_support_documents_per_ticker
                ),
                "supporting_documents_are_not_active_catalysts": True,
            },
            "selected_counts": selected_counts,
            "support_counts": support_counts,
            "status_counts": status_counts,
            "selected_receipts": [
                str(value)
                for value in selected.get("rcept_no", pd.Series(dtype="string"))
            ],
            "support_receipts": [
                str(value)
                for value in all_support.get("rcept_no", pd.Series(dtype="string"))
            ],
            "documents": documents,
        }
        return replace(
            base,
            captured_at=captured_at,
            raw_opendart=raw,
            warnings=tuple(dict.fromkeys(warnings)),
        )


__all__ = [
    "CORE_CATEGORIES",
    "DEFAULT_CORE_DOCUMENT_RESERVE",
    "DEFAULT_CORRECTION_DOCUMENT_RESERVE",
    "DOCUMENT_EVIDENCE_SCHEMA_VERSION",
    "FundamentalMacroCollector",
]
