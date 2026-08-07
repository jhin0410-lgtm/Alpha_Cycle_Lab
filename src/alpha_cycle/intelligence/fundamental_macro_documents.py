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
DOCUMENT_EVIDENCE_SCHEMA_VERSION = 2
_PERIODIC_REPORT_TOKENS = ("사업보고서", "분기보고서", "반기보고서")


def _is_periodic_report(report_name: object) -> bool:
    text = str(report_name).strip()
    return any(token in text for token in _PERIODIC_REPORT_TOKENS)


def _row_record(row: dict[str, object]) -> dict[str, object]:
    return {
        "ticker": str(row.get("ticker", "")).strip().zfill(6),
        "rcept_no": str(row.get("rcept_no", "")).strip(),
        "report_name": str(row.get("report_name", "")).strip(),
        "receipt_date": str(row.get("receipt_date", "")),
        "category": str(row.get("category", "")).strip(),
        "priority": str(row.get("priority", "")).strip(),
        "material_score": int(row.get("material_score", 0)),
        "is_correction": bool(row.get("is_correction", False)),
        "correction_chain_root_rcept_no": str(
            row.get("correction_chain_root_rcept_no", "")
        ).strip(),
        "correction_chain_order": int(row.get("correction_chain_order", 0)),
    }


def _selection_plan(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    max_documents_per_ticker: int,
) -> tuple[pd.DataFrame, dict[str, dict[str, object]], tuple[str, ...]]:
    if max_documents_per_ticker <= 0:
        raise ValueError("max_documents_per_ticker must be positive")
    events, catalysts, summary = classify_disclosures(
        disclosures,
        evaluation_date=evaluation_date,
        recent_days=365,
    )
    _, normalized, _, _ = normalize_disclosure_tables(events, catalysts, summary)
    if normalized.empty:
        return normalized.copy(), {}, ()

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
    return selected.reset_index(drop=True), ledger, tuple(warnings)


def select_material_disclosure_documents(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    max_documents_per_ticker: int = DEFAULT_MAX_DOCUMENTS_PER_TICKER,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Select latest-chain, high-materiality event filings for body collection."""

    selected, _, warnings = _selection_plan(
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
    ) -> None:
        super().__init__(opendart, ecos)
        if max_documents_per_ticker <= 0:
            raise ValueError("max_documents_per_ticker must be positive")
        self.document_client = document_client or OpenDartDisclosureDocumentClient(opendart)
        self.max_documents_per_ticker = max_documents_per_ticker

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
        selected, documents, selection_warnings = _selection_plan(
            base.disclosures,
            evaluation_date=evaluation_date,
            max_documents_per_ticker=self.max_documents_per_ticker,
        )

        raw_value = deepcopy(base.raw_opendart)
        if not isinstance(raw_value, dict):
            raise ValueError("OpenDART raw payload must be an object")
        raw = cast(dict[str, object], raw_value)
        warnings = [*base.warnings, *selection_warnings]
        captured_at = base.captured_at

        for row_value in selected.to_dict(orient="records"):
            row = {str(key): value for key, value in row_value.items()}
            ticker = str(row.get("ticker", "")).strip().zfill(6)
            receipt = str(row.get("rcept_no", "")).strip()
            record = documents.get(receipt)
            if record is None or record.get("status") != "selected_pending":
                raise ValueError("Disclosure document selection ledger binding mismatch")
            try:
                evidence = self.document_client.document(receipt)
            except (OSError, TypeError, ValueError) as exc:
                record.update(
                    {
                        "status": "unavailable",
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                    }
                )
                warnings.append(
                    f"disclosure_document_unavailable:{ticker}:{receipt}"
                )
            else:
                record.update({"status": "collected", **evidence.as_dict()})
                if evidence.retrieved_at > captured_at:
                    captured_at = evidence.retrieved_at
                for item in evidence.warnings:
                    warnings.append(
                        f"disclosure_document_warning:{ticker}:{receipt}:{item}"
                    )

        if any(record.get("status") == "selected_pending" for record in documents.values()):
            raise ValueError("Disclosure document selection contains unresolved pending records")
        selected_counts = {
            str(ticker).zfill(6): int(count)
            for ticker, count in selected.groupby("ticker", sort=True).size().items()
        } if not selected.empty else {}
        status_counts = dict(Counter(str(record.get("status", "unknown")) for record in documents.values()))
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
            },
            "selected_counts": selected_counts,
            "status_counts": status_counts,
            "selected_receipts": [
                str(value) for value in selected.get("rcept_no", pd.Series(dtype="string"))
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
    "FundamentalMacroCollector",
    "select_material_disclosure_documents",
]
