"""Resilient OpenDART share-count boundary for non-economic aggregate rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pandas as pd

from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_valuation import (
    OpenDartValuationClient as _BaseOpenDartValuationClient,
)
from alpha_cycle.providers.opendart_valuation import (
    StockTotalsBatch,
    _integer,
    _security_class,
)

_STOCK_TOTAL_PATH = "/api/stockTotqySttus.json"
_ECONOMIC_SECURITY_CLASSES = frozenset({"common", "preferred", "other"})
_NON_ECONOMIC_SECURITY_CLASSES = frozenset({"total", "note"})


class OpenDartValuationClient(_BaseOpenDartValuationClient):
    """Keep economic share classes strict while repairing empty aggregate rows.

    Some historical OpenDART responses contain a blank ``istc_totqy`` on a ``합계``
    or ``비고`` row even though common/preferred rows are complete. The aggregate row
    is not priced directly. A blank total is therefore derived from validated economic
    rows, while a note row is normalized to zero and remains excluded from valuation.
    Original values and derivation metadata stay in the raw payload.
    """

    def _json_get(
        self,
        path: str,
        query: Mapping[str, str],
        *,
        allow_no_data: bool = False,
    ) -> Mapping[str, object]:
        payload = super()._json_get(path, query, allow_no_data=allow_no_data)
        if path != _STOCK_TOTAL_PATH:
            return payload
        raw_rows = payload.get("list")
        if not isinstance(raw_rows, list):
            return payload

        rows: list[dict[str, object]] = []
        economic_counts: list[int] = []
        for raw_value in raw_rows:
            if not isinstance(raw_value, dict):
                return payload
            row = {str(key): value for key, value in raw_value.items()}
            rows.append(row)
            security_class = _security_class(row.get("se", ""))
            if security_class not in _ECONOMIC_SECURITY_CLASSES:
                continue
            count = _integer(row.get("istc_totqy"), "istc_totqy", optional=False)
            if count is None:
                raise ValueError("OpenDART economic istc_totqy cannot be missing")
            economic_counts.append(count)

        economic_total = sum(economic_counts) if economic_counts else None
        changed = False
        for row in rows:
            security_name = str(row.get("se", "")).strip()
            security_class = _security_class(security_name)
            if security_class not in _NON_ECONOMIC_SECURITY_CLASSES:
                continue
            try:
                _integer(row.get("istc_totqy"), "istc_totqy", optional=False)
                continue
            except ValueError:
                pass
            if security_class == "total":
                if economic_total is None:
                    raise ValueError(
                        "OpenDART aggregate istc_totqy is missing and no validated "
                        "economic share classes are available"
                    )
                replacement = economic_total
                source = "derived_validated_economic_class_sum"
            else:
                replacement = 0
                source = "non_economic_note_row_zero"
            original = row.get("istc_totqy")
            row["_alpha_cycle_original_istc_totqy"] = original
            row["_alpha_cycle_istc_totqy_source"] = source
            row["_alpha_cycle_istc_totqy_warning"] = (
                f"{security_name}: istc_totqy missing on {security_class} row; "
                f"normalized via {source}"
            )
            row["istc_totqy"] = str(replacement)
            changed = True

        if not changed:
            return payload
        repaired = dict(payload)
        repaired["list"] = rows
        return repaired

    def stock_totals(
        self,
        corp: CorpCode,
        *,
        business_year: int,
        report_code: str,
    ) -> StockTotalsBatch:
        batch = super().stock_totals(
            corp,
            business_year=business_year,
            report_code=report_code,
        )
        raw_payload = batch.raw_payload
        if not isinstance(raw_payload, dict):
            return batch
        raw_rows = raw_payload.get("list")
        if not isinstance(raw_rows, list):
            return batch

        frame = batch.frame.copy()
        warnings = list(batch.warnings)
        for raw_value in raw_rows:
            if not isinstance(raw_value, dict):
                continue
            raw = cast(Mapping[str, object], raw_value)
            warning = str(raw.get("_alpha_cycle_istc_totqy_warning", "")).strip()
            if not warning:
                continue
            warnings.append(f"{corp.stock_code}:{warning}")
            security_name = str(raw.get("se", "")).strip()
            mask = frame["security_name"].astype(str).eq(security_name)
            if not mask.any():
                continue
            existing = frame.loc[mask, "normalization_warning"].astype("string")
            frame.loc[mask, "normalization_warning"] = existing.fillna("").map(
                lambda value: f"{value} | {warning}".strip(" |")
            )

        diagnostic_payload = dict(raw_payload)
        diagnostic_payload["_normalization_warnings"] = list(warnings)
        return StockTotalsBatch(
            frame=frame,
            raw_payload=diagnostic_payload,
            corp=batch.corp,
            warnings=tuple(warnings),
        )


__all__ = ["OpenDartValuationClient"]
