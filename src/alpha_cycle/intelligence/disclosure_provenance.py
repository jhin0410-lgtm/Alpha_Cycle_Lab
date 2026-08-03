"""Normalize correction flags and build auditable disclosure lineage."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import cast

import pandas as pd

_CORRECTION_PREFIX = re.compile(
    r"^\s*(?:\[(?:기재정정|첨부정정|정정)\]|\((?:기재정정|첨부정정|정정)\)|"
    r"(?:기재정정|첨부정정|정정)\s*[:：])\s*"
)
_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "예", "정정"})
_FALSE_VALUES = frozenset({"0", "false", "f", "no", "n", "아니오", "일반"})
_PROVENANCE_COLUMNS = (
    "is_correction",
    "correction_flag_source",
    "correction_flag_conflict",
    "correction_base_report_name",
    "correction_family_key",
    "correction_parent_rcept_no",
    "correction_chain_root_rcept_no",
    "correction_chain_order",
    "correction_lineage_status",
    "correction_chain_event_count",
    "is_latest_in_correction_chain",
)


def _optional_bool(value: object) -> bool | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in {0, 1}:
            return bool(value)
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if value in {0.0, 1.0}:
            return bool(int(value))
        return None
    text = str(value).strip().casefold()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return None


def _base_report_name(report_name: str) -> str:
    result = report_name.strip()
    while result:
        stripped = _CORRECTION_PREFIX.sub("", result, count=1).strip()
        if stripped == result:
            break
        result = stripped
    return result


def _title_correction_flag(report_name: str) -> bool:
    return _base_report_name(report_name) != report_name.strip()


def _family_key(report_name: str) -> str:
    base = _base_report_name(report_name).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", base)


def _normalized_flag(raw: Mapping[str, object], report_name: str) -> tuple[bool, str, bool]:
    explicit = _optional_bool(raw.get("is_correction"))
    if report_name:
        title_flag = _title_correction_flag(report_name)
        return (
            title_flag,
            "report_name",
            explicit is not None and explicit != title_flag,
        )
    if explicit is not None:
        return explicit, "explicit_flag", False
    return False, "default_false", False


def _validate_events(events: pd.DataFrame) -> pd.DataFrame:
    required = {"ticker", "rcept_no", "report_name", "receipt_date"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(
            "Disclosure provenance requires columns: " + ", ".join(missing)
        )
    result = events.copy()
    result["ticker"] = result["ticker"].astype("string").str.strip().str.zfill(6)
    result["rcept_no"] = result["rcept_no"].astype("string").str.strip()
    if result["rcept_no"].duplicated().any():
        raise ValueError("Disclosure receipt numbers must be unique")
    result["report_name"] = result["report_name"].astype("string").fillna("").str.strip()
    result["receipt_date"] = pd.to_datetime(
        result["receipt_date"], errors="raise"
    ).dt.date
    return result.sort_values(
        ["ticker", "receipt_date", "rcept_no"], kind="stable"
    ).reset_index(drop=True)


def _add_flags(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_value in events.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        report_name = str(raw.get("report_name", "")).strip()
        is_correction, source, conflict = _normalized_flag(raw, report_name)
        raw.update(
            {
                "is_correction": is_correction,
                "correction_flag_source": source,
                "correction_flag_conflict": conflict,
                "correction_base_report_name": _base_report_name(report_name),
                "correction_family_key": _family_key(report_name),
            }
        )
        rows.append(raw)
    return pd.DataFrame(rows)


def _add_lineage(events: pd.DataFrame, *, lineage_days: int) -> pd.DataFrame:
    if lineage_days <= 0:
        raise ValueError("lineage_days must be positive")
    history: dict[tuple[str, str], list[dict[str, object]]] = {}
    rows: list[dict[str, object]] = []
    for raw_value in events.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        ticker = str(raw["ticker"])
        family = str(raw["correction_family_key"])
        rcept_no = str(raw["rcept_no"])
        receipt_date = cast(date, raw["receipt_date"])
        family_history = history.setdefault((ticker, family), [])
        is_correction = bool(raw["is_correction"])
        parent: dict[str, object] | None = None
        if is_correction:
            for candidate in reversed(family_history):
                candidate_date = cast(date, candidate["receipt_date"])
                age = (receipt_date - candidate_date).days
                if 0 <= age <= lineage_days:
                    parent = candidate
                    break
                if age > lineage_days:
                    break
        if not is_correction:
            parent_rcept_no: str | None = None
            root_rcept_no = rcept_no
            chain_order = 0
            lineage_status = "original"
        elif parent is None:
            parent_rcept_no = None
            root_rcept_no = rcept_no
            chain_order = 1
            lineage_status = "orphan_correction"
        else:
            parent_rcept_no = str(parent["rcept_no"])
            root_rcept_no = str(parent["correction_chain_root_rcept_no"])
            chain_order = cast(int, parent["correction_chain_order"]) + 1
            lineage_status = "linked_correction"
        raw.update(
            {
                "correction_parent_rcept_no": parent_rcept_no,
                "correction_chain_root_rcept_no": root_rcept_no,
                "correction_chain_order": chain_order,
                "correction_lineage_status": lineage_status,
            }
        )
        rows.append(raw)
        family_history.append(raw)

    result = pd.DataFrame(rows)
    chain_keys = ["ticker", "correction_chain_root_rcept_no"]
    result["correction_chain_event_count"] = result.groupby(
        chain_keys, sort=False
    )["rcept_no"].transform("size")
    result["is_latest_in_correction_chain"] = False
    latest_indices = (
        result.sort_values(
            [*chain_keys, "correction_chain_order", "receipt_date", "rcept_no"],
            kind="stable",
        )
        .groupby(chain_keys, sort=False)
        .tail(1)
        .index
    )
    result.loc[latest_indices, "is_latest_in_correction_chain"] = True
    return result.sort_values(
        ["ticker", "receipt_date", "rcept_no"], kind="stable"
    ).reset_index(drop=True)


def _normalized_catalysts(catalysts: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    context = events.loc[:, ["ticker", "rcept_no", *_PROVENANCE_COLUMNS]].copy()
    if catalysts.empty:
        result = catalysts.copy()
        for column in _PROVENANCE_COLUMNS:
            if column not in result.columns:
                result[column] = pd.Series(dtype=context[column].dtype)
        return result
    result = catalysts.drop(
        columns=[column for column in _PROVENANCE_COLUMNS if column in catalysts.columns]
    ).copy()
    result["ticker"] = result["ticker"].astype("string").str.strip().str.zfill(6)
    result["rcept_no"] = result["rcept_no"].astype("string").str.strip()
    result["_source_order"] = range(len(result))
    result = result.merge(
        context,
        on=["ticker", "rcept_no"],
        how="left",
        validate="many_to_one",
    )
    return result.sort_values("_source_order", kind="stable").drop(
        columns="_source_order"
    ).reset_index(drop=True)


def _normalized_summary(summary: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    result = summary.copy()
    if "ticker" not in result.columns:
        result["ticker"] = pd.Series(dtype="string")
    result["ticker"] = result["ticker"].astype("string").str.strip().str.zfill(6)
    diagnostics = (
        events.groupby("ticker", sort=True)
        .agg(
            correction_disclosures=("is_correction", "sum"),
            correction_flag_conflicts=("correction_flag_conflict", "sum"),
            orphan_corrections=(
                "correction_lineage_status",
                lambda values: int((values == "orphan_correction").sum()),
            ),
        )
        .reset_index()
    )
    result = result.drop(
        columns=[
            column
            for column in (
                "correction_disclosures",
                "correction_flag_conflicts",
                "orphan_corrections",
            )
            if column in result.columns
        ]
    )
    return result.merge(
        diagnostics,
        on="ticker",
        how="outer",
        validate="one_to_one",
    ).sort_values("ticker", kind="stable").reset_index(drop=True)


def normalize_disclosure_tables(
    events: pd.DataFrame,
    catalysts: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    lineage_days: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    """Normalize correction evidence before decision snapshots are persisted."""

    if events.empty:
        return events.copy(), catalysts.copy(), summary.copy(), ()
    normalized_events = _add_lineage(
        _add_flags(_validate_events(events)),
        lineage_days=lineage_days,
    )
    normalized_catalysts = _normalized_catalysts(catalysts, normalized_events)
    normalized_summary = _normalized_summary(summary, normalized_events)
    conflict_count = int(normalized_events["correction_flag_conflict"].sum())
    orphan_count = int(
        normalized_events["correction_lineage_status"].eq("orphan_correction").sum()
    )
    warnings: list[str] = []
    if conflict_count:
        warnings.append(f"disclosure_correction_flag_conflicts:{conflict_count}")
    if orphan_count:
        warnings.append(f"disclosure_orphan_corrections:{orphan_count}")
    return (
        normalized_events,
        normalized_catalysts,
        normalized_summary,
        tuple(warnings),
    )


__all__ = ["normalize_disclosure_tables"]
