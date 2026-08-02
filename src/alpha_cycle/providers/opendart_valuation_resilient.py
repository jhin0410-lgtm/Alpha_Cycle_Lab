"""Resilient OpenDART share-count boundary for ambiguous non-priced rows."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import cast

import pandas as pd

from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_valuation import (
    OpenDartValuationClient as _BaseOpenDartValuationClient,
)
from alpha_cycle.providers.opendart_valuation import (
    StockTotalsBatch,
    _candidate_periods,
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


def _derived_economic_share_count(
    row: Mapping[str, object],
) -> tuple[int, str] | None:
    """Recover issued shares only when official share identities are consistent."""

    candidates: list[tuple[str, int]] = []
    issued_to_date = _whole_share_or_none(row.get("now_to_isu_stock_totqy"))
    reduced_to_date = _whole_share_or_none(row.get("now_to_dcrs_stock_totqy"))
    if (
        issued_to_date is not None
        and reduced_to_date is not None
        and issued_to_date >= reduced_to_date
    ):
        candidates.append(
            ("derived_issued_minus_reduced", issued_to_date - reduced_to_date)
        )

    treasury_shares = _whole_share_or_none(row.get("tesstk_co"))
    floating_shares = _whole_share_or_none(row.get("distb_stock_co"))
    if treasury_shares is not None and floating_shares is not None:
        candidates.append(
            ("derived_treasury_plus_floating", treasury_shares + floating_shares)
        )

    if not candidates:
        return None
    values = {value for _, value in candidates}
    if len(values) != 1:
        return None
    value = values.pop()
    source = (
        "derived_cross_checked_share_identity"
        if len(candidates) > 1
        else candidates[0][0]
    )
    return value, source


def _set_repaired_issued_count(
    row: dict[str, object],
    *,
    security_name: str,
    replacement: int,
    source: str,
) -> None:
    original = row.get("istc_totqy")
    row["_alpha_cycle_original_istc_totqy"] = original
    row["_alpha_cycle_istc_totqy_source"] = source
    if source.startswith("derived_"):
        warning = (
            f"{security_name or '<blank>'}: istc_totqy could not be parsed; "
            f"validated as {replacement} via {source}"
        )
    else:
        warning = (
            f"{security_name or '<blank>'}: istc_totqy could not be validated; "
            f"schema value set to zero via {source}"
        )
    row["_alpha_cycle_istc_totqy_warning"] = warning
    row["istc_totqy"] = str(replacement)


def _usable_economic_stock_frame(frame: pd.DataFrame) -> bool:
    """Return whether a visible stock-total frame can safely support valuation."""

    if frame.empty:
        return False
    economic = frame.loc[
        frame["security_class"].astype("string").isin(_ECONOMIC_SECURITY_CLASSES)
    ]
    if economic.empty:
        return False
    issued = pd.to_numeric(economic["issued_shares"], errors="coerce")
    warnings = economic["normalization_warning"].astype("string").fillna("")
    unresolved = warnings.str.contains(_UNRESOLVED_ECONOMIC_SOURCE, regex=False)
    return bool(issued.gt(0).any() and not unresolved.any())


class OpenDartValuationClient(_BaseOpenDartValuationClient):
    """Preserve ambiguous share rows without manufacturing usable share counts.

    OpenDART historical ``stockTotqySttus`` payloads can contain blank or narrative
    ``istc_totqy`` values. For an economic security row, the official schema also
    exposes two independent identities: issued-to-date minus reduced-to-date, and
    treasury shares plus floating shares. A missing issued-share count is recovered
    only when the available identities agree. A blank class can additionally be proven
    to be zero, or recovered as a single residual class, when an explicit aggregate
    issued-share total reconciles exactly to all known economic classes.

    Some filings expose only aggregate and note rows. Those periods cannot identify the
    priced economic classes, so ``latest_stock_totals`` walks backward to the newest
    visible period with complete economic-class evidence. If none exists, it returns
    the latest visible evidence unchanged so the valuation guard still fails closed.
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
        for raw_value in raw_rows:
            if not isinstance(raw_value, dict):
                return payload
            rows.append({str(key): value for key, value in raw_value.items()})

        changed = False
        valid_economic_counts: list[int] = []
        unresolved_economic_rows: list[dict[str, object]] = []
        total_rows: list[dict[str, object]] = []

        for row in rows:
            security_name = str(row.get("se", "")).strip()
            security_class = _security_class(security_name)
            if security_class == "total":
                total_rows.append(row)
            if security_class not in _ECONOMIC_SECURITY_CLASSES:
                continue
            count = _whole_share_or_none(row.get("istc_totqy"))
            if count is None:
                derived = _derived_economic_share_count(row)
                if derived is None:
                    unresolved_economic_rows.append(row)
                    continue
                replacement, source = derived
                _set_repaired_issued_count(
                    row,
                    security_name=security_name,
                    replacement=replacement,
                    source=source,
                )
                count = replacement
                changed = True
            valid_economic_counts.append(count)

        explicit_total = (
            _whole_share_or_none(total_rows[0].get("istc_totqy"))
            if len(total_rows) == 1
            else None
        )
        unresolved_economic_names: list[str] = []
        if unresolved_economic_rows and explicit_total is not None:
            residual = explicit_total - sum(valid_economic_counts)
            if residual == 0:
                for row in unresolved_economic_rows:
                    security_name = str(row.get("se", "")).strip()
                    _set_repaired_issued_count(
                        row,
                        security_name=security_name,
                        replacement=0,
                        source="derived_zero_total_residual",
                    )
                    valid_economic_counts.append(0)
                unresolved_economic_rows = []
                changed = True
            elif residual > 0 and len(unresolved_economic_rows) == 1:
                row = unresolved_economic_rows.pop()
                security_name = str(row.get("se", "")).strip()
                _set_repaired_issued_count(
                    row,
                    security_name=security_name,
                    replacement=residual,
                    source="derived_single_class_total_residual",
                )
                valid_economic_counts.append(residual)
                changed = True

        for row in unresolved_economic_rows:
            security_name = str(row.get("se", "")).strip()
            unresolved_economic_names.append(security_name or "<blank>")
            _set_repaired_issued_count(
                row,
                security_name=security_name,
                replacement=0,
                source=_UNRESOLVED_ECONOMIC_SOURCE,
            )
            valid_economic_counts.append(0)
            changed = True

        for row in rows:
            if _whole_share_or_none(row.get("istc_totqy")) is not None:
                continue
            security_name = str(row.get("se", "")).strip()
            security_class = _security_class(security_name)
            if security_class in _ECONOMIC_SECURITY_CLASSES:
                continue
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
            _set_repaired_issued_count(
                row,
                security_name=security_name,
                replacement=replacement,
                source=source,
            )
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

    def latest_stock_totals(
        self,
        corp: CorpCode,
        *,
        evaluation_date: date,
    ) -> StockTotalsBatch:
        """Select the newest visible period with usable economic-class evidence."""

        attempts: list[dict[str, object]] = []
        newest_visible_unusable: StockTotalsBatch | None = None
        skipped_visible_periods: list[str] = []

        for business_year, report_code in _candidate_periods(evaluation_date, 2):
            batch = self.stock_totals(
                corp,
                business_year=business_year,
                report_code=report_code,
            )
            attempt: dict[str, object] = {
                "business_year": business_year,
                "report_code": report_code,
                "raw_payload": batch.raw_payload,
                "selection_status": "empty",
            }
            attempts.append(attempt)
            if batch.frame.empty:
                continue
            visible = batch.frame.loc[
                (batch.frame["period_end"] <= evaluation_date)
                & (batch.frame["available_date"] <= evaluation_date)
            ].copy()
            if visible.empty:
                attempt["selection_status"] = "not_visible"
                continue
            if _usable_economic_stock_frame(visible):
                attempt["selection_status"] = "selected_usable"
                warnings = list(batch.warnings)
                if skipped_visible_periods:
                    warnings.append(
                        f"{corp.stock_code}: selected older usable stock-total period "
                        f"{business_year}/{report_code} after unusable newer periods "
                        f"{','.join(skipped_visible_periods)}"
                    )
                return StockTotalsBatch(
                    visible.reset_index(drop=True),
                    {"selected": batch.raw_payload, "attempts": attempts},
                    corp,
                    tuple(warnings),
                )

            attempt["selection_status"] = "visible_unusable"
            skipped_visible_periods.append(f"{business_year}/{report_code}")
            if newest_visible_unusable is None:
                newest_visible_unusable = StockTotalsBatch(
                    visible.reset_index(drop=True),
                    batch.raw_payload,
                    corp,
                    batch.warnings,
                )

        if newest_visible_unusable is not None:
            warnings = list(newest_visible_unusable.warnings)
            warnings.append(
                f"{corp.stock_code}: no usable economic-class stock-total period was "
                "available; latest visible evidence retained fail-closed"
            )
            return StockTotalsBatch(
                newest_visible_unusable.frame,
                {
                    "selected": newest_visible_unusable.raw_payload,
                    "attempts": attempts,
                },
                corp,
                tuple(warnings),
            )

        raise ValueError(
            f"No OpenDART stock totals were available by {evaluation_date} "
            f"for {corp.stock_code}"
        )


__all__ = ["OpenDartValuationClient"]
