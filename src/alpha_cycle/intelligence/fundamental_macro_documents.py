"""Add bounded OpenDART original-document evidence to research snapshots."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence.decision_features import classify_disclosures
from alpha_cycle.intelligence.disclosure_provenance import normalize_disclosure_tables
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroCollector as BaseFundamentalMacroCollector,
)
from alpha_cycle.intelligence.fundamental_macro import FundamentalMacroSnapshot
from alpha_cycle.providers.ecos import EcosReadOnlyClient, EcosSeriesSpec
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import OpenDartDisclosureDocumentClient

DEFAULT_MAX_DOCUMENTS_PER_TICKER = 12
DEFAULT_MAX_SUPPORT_DOCUMENTS_PER_TICKER = 24
MAX_CORRECTION_ANCESTORS_PER_SELECTED = 4
DOCUMENT_EVIDENCE_SCHEMA_VERSION = 3
_PERIODIC_REPORT_TOKENS = ("사업보고서", "분기보고서", "반기보고서")


def _is_periodic_report(report_name: object) -> bool:
    text = str(report_name).strip()
    return any(token in text for token in _PERIODIC_REPORT_TOKENS)


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Disclosure document {field} must be an integer")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text and text.removeprefix("-").isdigit():
        return int(text)
    try:
        numeric = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Disclosure document {field} must be an integer") from exc
    if not numeric.is_integer():
        raise ValueError(f"Disclosure document {field} must be an integer")
    return int(numeric)


def _row_record(row: dict[str, object]) -> dict[str, object]:
    return {
        "ticker": str(row.get("ticker", "")).strip().zfill(6),
        "rcept_no": str(row.get("rcept_no", "")).strip(),
        "report_name": str(row.get("report_name", "")).strip(),
        "receipt_date": str(row.get("receipt_date", "")),
        "category": str(row.get("category", "")).strip(),
        "priority": str(row.get("priority", "")).strip(),
        "material_score": _integer(
            row.get("material_score", 0),
            field="material_score",
        ),
        "is_correction": bool(row.get("is_correction", False)),
        "correction_family_key": str(
            row.get("correction_family_key", "")
        ).strip(),
        "correction_parent_rcept_no": str(
            row.get("correction_parent_rcept_no", "") or ""
        ).strip(),
        "correction_chain_root_rcept_no": str(
            row.get("correction_chain_root_rcept_no", "")
        ).strip(),
        "correction_chain_order": _integer(
            row.get("correction_chain_order", 0),
            field="correction_chain_order",
        ),
        "correction_lineage_status": str(
            row.get("correction_lineage_status", "")
        ).strip(),
        "is_latest_in_correction_chain": bool(
            row.get("is_latest_in_correction_chain", True)
        ),
    }


def _event_lookup(events: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for raw_value in events.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        receipt = str(raw.get("rcept_no", "")).strip()
        if not receipt or receipt in lookup:
            raise ValueError("Disclosure correction lineage requires unique receipt numbers")
        lookup[receipt] = raw
    return lookup


def _correction_support_plan(
    selected: pd.DataFrame,
    events: pd.DataFrame,
    *,
    max_support_documents_per_ticker: int,
) -> tuple[pd.DataFrame, dict[str, list[str]], tuple[str, ...]]:
    """Resolve bounded validated ancestors for selected correction filings."""

    if max_support_documents_per_ticker <= 0:
        raise ValueError("max_support_documents_per_ticker must be positive")
    if selected.empty:
        return events.iloc[0:0].copy(), {}, ()

    lookup = _event_lookup(events)
    candidates: dict[str, dict[str, object]] = {}
    supporters: dict[str, list[str]] = {}
    candidate_order: dict[str, list[str]] = {}
    warnings: list[str] = []

    for raw_value in selected.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        if not bool(raw.get("is_correction", False)):
            continue
        ticker = str(raw.get("ticker", "")).strip().zfill(6)
        selected_receipt = str(raw.get("rcept_no", "")).strip()
        lineage_status = str(raw.get("correction_lineage_status", "")).strip()
        parent_receipt = str(raw.get("correction_parent_rcept_no", "") or "").strip()
        if lineage_status != "linked_correction" or not parent_receipt:
            warnings.append(
                "disclosure_correction_support_orphan:"
                f"{ticker}:{selected_receipt}:{lineage_status or 'unknown'}"
            )
            continue

        family = str(raw.get("correction_family_key", "")).strip()
        root = str(raw.get("correction_chain_root_rcept_no", "")).strip()
        expected_order = _integer(
            raw.get("correction_chain_order", 0),
            field="correction_chain_order",
        ) - 1
        visited = {selected_receipt}
        ancestor_count = 0

        while parent_receipt:
            if ancestor_count >= MAX_CORRECTION_ANCESTORS_PER_SELECTED:
                warnings.append(
                    "disclosure_correction_support_ancestor_truncated:"
                    f"{ticker}:{selected_receipt}:{MAX_CORRECTION_ANCESTORS_PER_SELECTED}"
                )
                break
            if parent_receipt in visited:
                raise ValueError("Disclosure correction lineage contains a cycle")
            visited.add(parent_receipt)
            parent = lookup.get(parent_receipt)
            if parent is None:
                warnings.append(
                    "disclosure_correction_support_missing_parent:"
                    f"{ticker}:{selected_receipt}:{parent_receipt}"
                )
                break

            parent_ticker = str(parent.get("ticker", "")).strip().zfill(6)
            parent_family = str(parent.get("correction_family_key", "")).strip()
            parent_root = str(
                parent.get("correction_chain_root_rcept_no", "")
            ).strip()
            parent_order = _integer(
                parent.get("correction_chain_order", 0),
                field="correction_chain_order",
            )
            if (
                parent_ticker != ticker
                or parent_family != family
                or parent_root != root
                or parent_order != expected_order
            ):
                warnings.append(
                    "disclosure_correction_support_lineage_mismatch:"
                    f"{ticker}:{selected_receipt}:{parent_receipt}"
                )
                break

            if parent_receipt not in candidates:
                candidates[parent_receipt] = parent
                candidate_order.setdefault(ticker, []).append(parent_receipt)
            supporter_list = supporters.setdefault(parent_receipt, [])
            if selected_receipt not in supporter_list:
                supporter_list.append(selected_receipt)

            ancestor_count += 1
            if parent_order == 0:
                break
            expected_order = parent_order - 1
            parent_receipt = str(
                parent.get("correction_parent_rcept_no", "") or ""
            ).strip()
            if not parent_receipt:
                warnings.append(
                    "disclosure_correction_support_missing_parent:"
                    f"{ticker}:{selected_receipt}:order_{parent_order}"
                )
                break

    kept_receipts: set[str] = set()
    for ticker, receipts in candidate_order.items():
        kept = receipts[:max_support_documents_per_ticker]
        kept_receipts.update(kept)
        if len(receipts) > max_support_documents_per_ticker:
            warnings.append(
                "disclosure_correction_support_capacity_truncated:"
                f"{ticker}:{max_support_documents_per_ticker}/{len(receipts)}"
            )

    rows = [
        candidates[receipt]
        for receipt in candidates
        if receipt in kept_receipts
    ]
    support = pd.DataFrame(rows)
    if support.empty:
        support = events.iloc[0:0].copy()
    else:
        support = support.reindex(columns=events.columns)
    kept_supporters = {
        receipt: supporters[receipt]
        for receipt in supporters
        if receipt in kept_receipts
    }
    return support.reset_index(drop=True), kept_supporters, tuple(warnings)


def _selection_plan(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    max_documents_per_ticker: int,
    max_support_documents_per_ticker: int = DEFAULT_MAX_SUPPORT_DOCUMENTS_PER_TICKER,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, dict[str, object]],
    tuple[str, ...],
]:
    if max_documents_per_ticker <= 0:
        raise ValueError("max_documents_per_ticker must be positive")
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
        return normalized.copy(), normalized_events.iloc[0:0].copy(), {}, ()

    ordered = normalized.sort_values(
        ["ticker", "material_score", "receipt_date", "rcept_no"],
        ascending=[True, False, False, False],
        kind="stable",
    ).reset_index(drop=True)
    ledger: dict[str, dict[str, object]] = {}
    selected_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for ticker, group in ordered.groupby("ticker", sort=True):
        eligible_used = 0
        eligible_total = int((~group["report_name"].map(_is_periodic_report)).sum())
        for raw_value in group.to_dict(orient="records"):
            raw = {str(key): value for key, value in raw_value.items()}
            record = _row_record(raw)
            receipt = str(record["rcept_no"])
            if not receipt or receipt in ledger:
                raise ValueError("Disclosure document selection requires unique receipt numbers")
            record["role"] = "primary_catalyst"
            if _is_periodic_report(record["report_name"]):
                record.update(
                    {
                        "status": "excluded_periodic",
                        "selection_reason": "periodic_report_financial_evidence_path",
                    }
                )
            elif eligible_used < max_documents_per_ticker:
                eligible_used += 1
                record.update(
                    {
                        "status": "selected_pending",
                        "selection_reason": "bounded_material_event_selection",
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

    support, supporters, support_warnings = _correction_support_plan(
        selected,
        normalized_events,
        max_support_documents_per_ticker=max_support_documents_per_ticker,
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
        ledger,
        tuple(dict.fromkeys(warnings)),
    )


def select_material_disclosure_documents(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    max_documents_per_ticker: int = DEFAULT_MAX_DOCUMENTS_PER_TICKER,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Select latest-chain, high-materiality event filings for body collection."""

    selected, _, _, warnings = _selection_plan(
        disclosures,
        evaluation_date=evaluation_date,
        max_documents_per_ticker=max_documents_per_ticker,
    )
    return selected, warnings


class FundamentalMacroCollector(BaseFundamentalMacroCollector):
    """Base official-data collector plus bounded immutable filing-body evidence."""

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
        selected, support, documents, selection_warnings = _selection_plan(
            base.disclosures,
            evaluation_date=evaluation_date,
            max_documents_per_ticker=self.max_documents_per_ticker,
            max_support_documents_per_ticker=self.max_support_documents_per_ticker,
        )

        raw_value = deepcopy(base.raw_opendart)
        if not isinstance(raw_value, dict):
            raise ValueError("OpenDART raw payload must be an object")
        raw = cast(dict[str, object], raw_value)
        warnings = [*base.warnings, *selection_warnings]
        captured_at = base.captured_at

        download_plan: list[tuple[pd.DataFrame, str, str, str]] = [
            (selected, "selected_pending", "unavailable", "disclosure_document_unavailable"),
            (
                support,
                "selected_support_pending",
                "support_unavailable",
                "disclosure_correction_support_unavailable",
            ),
        ]
        for frame, pending_status, failure_status, warning_prefix in download_plan:
            for row_value in frame.to_dict(orient="records"):
                row = {str(key): value for key, value in row_value.items()}
                ticker = str(row.get("ticker", "")).strip().zfill(6)
                receipt = str(row.get("rcept_no", "")).strip()
                record = documents.get(receipt)
                if record is None:
                    raise ValueError("Disclosure document selection ledger binding mismatch")
                if record.get("status") != pending_status:
                    if (
                        pending_status == "selected_support_pending"
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
                    if evidence.retrieved_at > captured_at:
                        captured_at = evidence.retrieved_at
                    for item in evidence.warnings:
                        warnings.append(
                            f"disclosure_document_warning:{ticker}:{receipt}:{item}"
                        )

        pending_statuses = {"selected_pending", "selected_support_pending"}
        if any(record.get("status") in pending_statuses for record in documents.values()):
            raise ValueError("Disclosure document selection contains unresolved pending records")

        selected_counts = {
            str(ticker).zfill(6): int(count)
            for ticker, count in selected.groupby("ticker", sort=True).size().items()
        } if not selected.empty else {}
        support_counts = {
            str(ticker).zfill(6): int(count)
            for ticker, count in support.groupby("ticker", sort=True).size().items()
        } if not support.empty else {}
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
                "correction_parent_support_enabled": True,
                "max_correction_ancestors_per_selected": (
                    MAX_CORRECTION_ANCESTORS_PER_SELECTED
                ),
                "max_support_documents_per_ticker": (
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
                for value in support.get("rcept_no", pd.Series(dtype="string"))
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
    "DEFAULT_MAX_DOCUMENTS_PER_TICKER",
    "DEFAULT_MAX_SUPPORT_DOCUMENTS_PER_TICKER",
    "FundamentalMacroCollector",
    "MAX_CORRECTION_ANCESTORS_PER_SELECTED",
    "select_material_disclosure_documents",
]
