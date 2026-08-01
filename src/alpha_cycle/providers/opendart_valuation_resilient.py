"""Resilient OpenDART share-count boundary for ambiguous non-priced rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

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
_UNRESOLVED_ECONOMIC_SOURCE = "unresolved_missing_economic_share_count"


def _whole_share_or_none(value: object) -> int | None:
    try:
        return _integer(value, "istc_totqy", optional=False)
    except ValueError:
        return None


class OpenDartValuationClient(_BaseOpenDartValuationClient):
    """Preserve ambiguous share rows without manufacturing usable share counts.

    OpenDART historical ``stockTotqySttus`` payloads can contain blank or narrative
    ``istc_totqy`` values on labels that are not consistently named ``합계`` or ``비고``.
    The base parser requires a whole-share integer for every row, so those provider
    anomalies previously aborted the entire live pipeline before the valuation layer
    could decide whether the row was actually price-relevant.

    This boundary replaces an unparseable row with a schema-safe zero only so the raw
    evidence can travel through the pipeline. The original value and an explicit source
    marker are preserved. A later valuation guard treats any unresolved economic row as
    incomplete evidence and clears market capitalization and valuation multiples.
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
        valid_economic_counts: list[int] = []
        unresolved_economic_names: list[str] = []
        for raw_value in raw_rows:
            if not isinstance(raw_value, dict):
                return payload
            row = {str(key): value for key, value in raw_value.items()}
            rows.append(row)
            security_name = str(row.get("se", "")).strip()
            security_class = _security_class(security_name)
            if security_class not in _ECONOMIC_SECURITY_CLASSES:
                continue
            count = _whole_share_or_none(row.get("istc_totqy"))
            if count is None:
                unresolved_economic_names.append(security_name or "<blank>")
            else:
                valid_economic_counts.append(count)

        changed = False
        for row in rows:
            if _whole_share_or_none(row.get("istc_totqy")) is not None:
                continue
            security_name = str(row.get("se", "")).strip()
            security_class = _security_class(security_name)
            can_derive_total = (
                security_class == "total"
                and bool(valid_economic_counts)
                and not unresolved_economic_names
            )
            if can_derive_total:
                replacement = sum(valid_economic_counts)
                source = "derived_validated_economic_class_sum"
            elif security_class == "note":
                replacement = 0
                source = "non_economic_note_row_zero"
            elif security_class == "total":
                replacement = 0
                source = "unresolved_aggregate_share_count"
            else:
                replacement = 0
                source = _UNRESOLVED_ECONOMIC_SOURCE
            original = row.get("istc_totqy")
            row["_alpha_cycle_original_istc_totqy"] = original
            row["_alpha_cycle_istc_totqy_source"] = source
            row["_alpha_cycle_istc_totqy_warning"] = (
                f"{security_name or '<blank>'}: istc_totqy could not be validated; "
                f"schema value set to zero via {source}"
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
            combined = [
                f"{value} | {warning}".strip(" |")
                for value in existing.fillna("").astype(str).tolist()
            ]
            frame.loc[mask, "normalization_warning"] = combined

        diagnostic_payload = dict(raw_payload)
        diagnostic_payload["_normalization_warnings"] = list(warnings)
        return StockTotalsBatch(
            frame=frame,
            raw_payload=diagnostic_payload,
            corp=batch.corp,
            warnings=tuple(warnings),
        )


__all__ = ["OpenDartValuationClient"]
