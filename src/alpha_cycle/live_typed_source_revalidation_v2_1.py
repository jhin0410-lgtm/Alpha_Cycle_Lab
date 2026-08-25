"""Canonical replay of persisted live market and research source snapshots.

These validators reconstruct the original snapshot dataclasses from the immutable files written
by the existing live writers and compare the recomputed content identity with the persisted
manifest. A manifest-declared snapshot id is never treated as authority by itself.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_cycle.data.research import (
    FINANCIAL_OPTIONAL,
    FINANCIAL_REQUIRED,
    MACRO_REQUIRED,
    RevisionPolicy,
    validate_financial_statements,
    validate_macro_series,
)
from alpha_cycle.intelligence.fundamental_macro import (
    RESEARCH_INTELLIGENCE_SCHEMA_VERSION,
    FundamentalMacroSnapshot,
)
from alpha_cycle.intelligence.market import SNAPSHOT_SCHEMA_VERSION, MarketIntelligenceSnapshot
from alpha_cycle.intelligence.technical import TechnicalFeatures
from alpha_cycle.providers.tossinvest import Candle, MarketPrice

_MARKET_FILES = (
    "prices.csv",
    "candles.csv",
    "technical_features.csv",
    "raw_prices.json",
    "raw_candles.json",
)
_RESEARCH_FILES = (
    "financials.csv",
    "disclosures.csv",
    "macro.csv",
    "raw_opendart.json",
    "raw_ecos.json",
)
_KOREA_TZ = ZoneInfo("Asia/Seoul")


class LiveTypedSourceRevalidationError(ValueError):
    """Raised when persisted live-source bytes do not reconstruct their declared snapshot."""


def revalidate_market_snapshot(directory: str | Path) -> MarketIntelligenceSnapshot:
    """Reconstruct a persisted market snapshot and require exact canonical identity."""

    root = _trusted_snapshot_directory(Path(directory))
    manifest = _load_object(root / "manifest.json")
    _require_exact_fields(
        manifest,
        {
            "schema_version",
            "snapshot_id",
            "captured_at",
            "provider",
            "interval",
            "adjusted",
            "symbols",
            "files",
            "order_api_enabled",
        },
        "market manifest",
    )
    if _required_int(manifest, "schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise LiveTypedSourceRevalidationError("unsupported market snapshot schema")
    if manifest.get("order_api_enabled") is not False:
        raise LiveTypedSourceRevalidationError("market snapshot must remain read-only")
    if _required_string_list(manifest, "files") != list(_MARKET_FILES):
        raise LiveTypedSourceRevalidationError(
            "market manifest file set differs from writer contract"
        )

    prices = tuple(
        MarketPrice(
            symbol=_cell(row, "symbol"),
            timestamp=_aware_datetime(_cell(row, "timestamp"), "price timestamp"),
            last_price=Decimal(_cell(row, "last_price")),
            currency=_cell(row, "currency"),
        )
        for row in _read_csv_rows(root / "prices.csv")
    )
    candles = tuple(
        Candle(
            symbol=_cell(row, "symbol"),
            timestamp=_aware_datetime(_cell(row, "timestamp"), "candle timestamp"),
            open_price=Decimal(_cell(row, "open")),
            high_price=Decimal(_cell(row, "high")),
            low_price=Decimal(_cell(row, "low")),
            close_price=Decimal(_cell(row, "close")),
            volume=Decimal(_cell(row, "volume")),
            currency=_cell(row, "currency"),
            interval=_cell(row, "interval"),
            adjusted=_bool(_cell(row, "adjusted"), "candle adjusted"),
        )
        for row in _read_csv_rows(root / "candles.csv")
    )
    features = tuple(
        _technical_feature(row)
        for row in _read_csv_rows(root / "technical_features.csv")
    )
    snapshot = MarketIntelligenceSnapshot(
        captured_at=_aware_datetime(_required_text(manifest, "captured_at"), "captured_at"),
        provider=_required_text(manifest, "provider"),
        interval=_required_text(manifest, "interval"),
        adjusted=_required_bool(manifest, "adjusted"),
        prices=prices,
        candles=candles,
        features=features,
        raw_prices=_load_json(root / "raw_prices.json"),
        raw_candles=_string_object(
            _load_json(root / "raw_candles.json"), "raw_candles"
        ),
    )
    future_price = any(item.timestamp > snapshot.captured_at for item in snapshot.prices)
    future_candle = any(item.timestamp > snapshot.captured_at for item in snapshot.candles)
    if future_price or future_candle:
        raise LiveTypedSourceRevalidationError(
            "market observation cannot follow market snapshot captured_at"
        )
    declared_id = _required_text(manifest, "snapshot_id")
    if snapshot.snapshot_id != declared_id:
        raise LiveTypedSourceRevalidationError("market snapshot canonical identity mismatch")
    if _required_string_list(manifest, "symbols") != list(snapshot.symbols):
        raise LiveTypedSourceRevalidationError(
            "market manifest symbols do not match canonical snapshot"
        )
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    expected_name = f"{timestamp}__{snapshot.snapshot_id[:12]}"
    if root.name != expected_name:
        raise LiveTypedSourceRevalidationError("market snapshot directory identity mismatch")
    return snapshot


def revalidate_research_snapshot(directory: str | Path) -> FundamentalMacroSnapshot:
    """Reconstruct a persisted OpenDART/ECOS snapshot and require canonical identity."""

    root = _trusted_snapshot_directory(Path(directory))
    manifest = _load_object(root / "manifest.json")
    _require_exact_fields(
        manifest,
        {
            "schema_version",
            "snapshot_id",
            "captured_at",
            "evaluation_date",
            "revision_policy",
            "market_snapshot_id",
            "financial_rows",
            "disclosure_rows",
            "macro_rows",
            "warnings",
            "research_mode",
            "historical_revision_archive_complete",
            "availability_policy",
            "files",
            "order_api_enabled",
        },
        "research manifest",
    )
    if _required_int(manifest, "schema_version") != RESEARCH_INTELLIGENCE_SCHEMA_VERSION:
        raise LiveTypedSourceRevalidationError("unsupported research snapshot schema")
    if manifest.get("order_api_enabled") is not False:
        raise LiveTypedSourceRevalidationError("research snapshot must remain read-only")
    if manifest.get("research_mode") != "live_endpoint_filtered":
        raise LiveTypedSourceRevalidationError("unsupported research snapshot mode")
    if manifest.get("historical_revision_archive_complete") is not False:
        raise LiveTypedSourceRevalidationError(
            "live research snapshot archive semantics changed"
        )
    expected_availability = {
        "opendart": "filing_receipt_date",
        "ecos": "korea_retrieval_date_conservative",
    }
    if manifest.get("availability_policy") != expected_availability:
        raise LiveTypedSourceRevalidationError(
            "research availability policy differs from writer contract"
        )
    if _required_string_list(manifest, "files") != list(_RESEARCH_FILES):
        raise LiveTypedSourceRevalidationError(
            "research manifest file set differs from writer contract"
        )

    financials = _read_financial_frame(root / "financials.csv")
    disclosures = _read_disclosure_frame(root / "disclosures.csv")
    macro = _read_macro_frame(root / "macro.csv")
    if len(financials) != _required_int(manifest, "financial_rows"):
        raise LiveTypedSourceRevalidationError("research financial row count mismatch")
    if len(disclosures) != _required_int(manifest, "disclosure_rows"):
        raise LiveTypedSourceRevalidationError("research disclosure row count mismatch")
    if len(macro) != _required_int(manifest, "macro_rows"):
        raise LiveTypedSourceRevalidationError("research macro row count mismatch")

    market_snapshot_raw = manifest.get("market_snapshot_id")
    market_snapshot_id = None
    if market_snapshot_raw is not None:
        market_snapshot_id = _text(market_snapshot_raw, "market_snapshot_id")
    warnings = tuple(_required_string_list(manifest, "warnings"))
    snapshot = FundamentalMacroSnapshot(
        captured_at=_aware_datetime(_required_text(manifest, "captured_at"), "captured_at"),
        evaluation_date=_date(_required_text(manifest, "evaluation_date"), "evaluation_date"),
        revision_policy=RevisionPolicy(_required_text(manifest, "revision_policy")),
        financials=financials,
        disclosures=disclosures,
        macro=macro,
        raw_opendart=_load_json(root / "raw_opendart.json"),
        raw_ecos=_load_json(root / "raw_ecos.json"),
        market_snapshot_id=market_snapshot_id,
        warnings=warnings,
    )
    _validate_research_point_in_time(snapshot)
    declared_id = _required_text(manifest, "snapshot_id")
    if snapshot.snapshot_id != declared_id:
        raise LiveTypedSourceRevalidationError("research snapshot canonical identity mismatch")
    timestamp = snapshot.captured_at.strftime("%Y%m%dT%H%M%S%fZ")
    expected_name = f"{timestamp}__{snapshot.snapshot_id[:12]}"
    if root.name != expected_name:
        raise LiveTypedSourceRevalidationError("research snapshot directory identity mismatch")
    return snapshot


def _validate_research_point_in_time(snapshot: FundamentalMacroSnapshot) -> None:
    captured = snapshot.captured_at
    captured_source_date = captured.astimezone(_KOREA_TZ).date()
    for frame, label in (
        (snapshot.financials, "financial"),
        (snapshot.macro, "macro"),
    ):
        for row in frame.to_dict(orient="records"):
            available = row.get("available_date")
            retrieved = row.get("retrieved_at")
            if not isinstance(available, date) or not isinstance(retrieved, pd.Timestamp):
                raise LiveTypedSourceRevalidationError(
                    f"{label} availability fields are not canonical"
                )
            retrieved_at = retrieved.to_pydatetime()
            if available > captured_source_date or retrieved_at > captured:
                raise LiveTypedSourceRevalidationError(
                    f"{label} observation cannot follow research snapshot captured_at"
                )
    if "receipt_date" in snapshot.disclosures.columns:
        for value in snapshot.disclosures["receipt_date"]:
            receipt_date = _date(str(value), "receipt_date")
            if receipt_date > snapshot.evaluation_date or receipt_date > captured_source_date:
                raise LiveTypedSourceRevalidationError(
                    "disclosure observation cannot follow research snapshot captured_at"
                )


def _technical_feature(row: dict[str, str]) -> TechnicalFeatures:
    return TechnicalFeatures(
        symbol=_cell(row, "symbol"),
        interval=_cell(row, "interval"),
        adjusted=_bool(_cell(row, "adjusted"), "feature adjusted"),
        observations=_integer(_cell(row, "observations"), "observations"),
        last_price=_float(_cell(row, "last_price"), "last_price"),
        return_1=_optional_float(row.get("return_1")),
        return_5=_optional_float(row.get("return_5")),
        return_20=_optional_float(row.get("return_20")),
        sma_5=_optional_float(row.get("sma_5")),
        sma_20=_optional_float(row.get("sma_20")),
        price_to_sma_20=_optional_float(row.get("price_to_sma_20")),
        realized_volatility_20=_optional_float(row.get("realized_volatility_20")),
        volume_ratio_20=_optional_float(row.get("volume_ratio_20")),
        drawdown_from_20_high=_optional_float(row.get("drawdown_from_20_high")),
        rsi_14=_optional_float(row.get("rsi_14")),
        trend_efficiency_20=_optional_float(row.get("trend_efficiency_20")),
        trend_direction_20=_optional_float(row.get("trend_direction_20")),
        relative_strength_rank_20=_optional_float(row.get("relative_strength_rank_20")),
    )


def _trusted_snapshot_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise LiveTypedSourceRevalidationError(f"snapshot must be a real directory: {path}")
    resolved = path.resolve()
    manifest = resolved / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise LiveTypedSourceRevalidationError("snapshot requires a regular manifest.json")
    return resolved


def _read_csv_rows(path: Path) -> tuple[dict[str, str], ...]:
    if path.is_symlink() or not path.is_file():
        raise LiveTypedSourceRevalidationError(
            f"snapshot CSV must be a regular file: {path}"
        )
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise LiveTypedSourceRevalidationError(f"snapshot CSV has no header: {path}")
        return tuple(
            {str(key): "" if value is None else value for key, value in row.items()}
            for row in reader
        )


def _read_frame(
    path: Path,
    *,
    dtype: str | dict[str, str] | None = None,
    empty_as_na: bool = True,
) -> pd.DataFrame:
    if path.is_symlink() or not path.is_file():
        raise LiveTypedSourceRevalidationError(
            f"snapshot CSV must be a regular file: {path}"
        )
    try:
        return pd.read_csv(
            path,
            dtype=dtype,
            float_precision="round_trip",
            keep_default_na=False,
            na_values=[""] if empty_as_na else None,
        )
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
        raise LiveTypedSourceRevalidationError(
            f"cannot decode snapshot CSV: {path}"
        ) from exc


def _read_financial_frame(path: Path) -> pd.DataFrame:
    frame = _read_frame(
        path,
        dtype={
            column: "string"
            for column in (
                "ticker",
                "metric",
                "fiscal_period",
                "unit",
                "source",
                "revision_id",
                "currency",
            )
        },
    )
    try:
        validated = validate_financial_statements(frame)
        return _restore_financial_row_order(validated, frame)
    except (TypeError, ValueError) as exc:
        raise LiveTypedSourceRevalidationError(
            "research financial CSV violates the canonical data contract"
        ) from exc


def _read_macro_frame(path: Path) -> pd.DataFrame:
    frame = _read_frame(
        path,
        dtype={
            column: "string"
            for column in ("series_id", "frequency", "unit", "source", "revision_id")
        },
    )
    try:
        validated = validate_macro_series(frame)
        return _restore_macro_row_order(validated, frame)
    except (TypeError, ValueError) as exc:
        raise LiveTypedSourceRevalidationError(
            "research macro CSV violates the canonical data contract"
        ) from exc


def _read_disclosure_frame(path: Path) -> pd.DataFrame:
    frame = _read_frame(
        path,
        dtype={
            column: "string"
            for column in (
                "ticker",
                "corp_code",
                "corp_name",
                "rcept_no",
                "report_name",
                "corp_class",
            )
        },
        empty_as_na=False,
    )
    if "receipt_date" in frame.columns:
        frame["receipt_date"] = pd.to_datetime(
            frame["receipt_date"], errors="raise"
        ).dt.date
    if "is_correction" in frame.columns:
        values = frame["is_correction"]
        if values.dtype != bool:
            mapping = {"True": True, "False": False}
            if not values.astype(str).isin(mapping).all():
                raise LiveTypedSourceRevalidationError(
                    "disclosure is_correction must be True or False"
                )
            frame["is_correction"] = values.astype(str).map(mapping).astype(bool)
    return frame


def _restore_financial_row_order(
    validated: pd.DataFrame,
    source: pd.DataFrame,
) -> pd.DataFrame:
    if validated.empty:
        return validated.loc[:, [*FINANCIAL_REQUIRED, *FINANCIAL_OPTIONAL]]

    def key(row: pd.Series[Any]) -> tuple[object, ...]:
        return (
            str(row["ticker"]).strip(),
            str(row["metric"]).strip(),
            pd.Timestamp(row["period_end"]).date(),
            str(row["fiscal_period"]).strip(),
            int(row["revision_sequence"]),
        )

    return _restore_validated_row_order(validated, source, key)


def _restore_macro_row_order(
    validated: pd.DataFrame,
    source: pd.DataFrame,
) -> pd.DataFrame:
    if validated.empty:
        return validated.loc[:, list(MACRO_REQUIRED)]

    def key(row: pd.Series[Any]) -> tuple[object, ...]:
        return (
            str(row["series_id"]).strip(),
            pd.Timestamp(row["observation_date"]).date(),
            int(row["revision_sequence"]),
        )

    return _restore_validated_row_order(validated, source, key)


def _restore_validated_row_order(
    validated: pd.DataFrame,
    source: pd.DataFrame,
    key: Callable[[pd.Series[Any]], tuple[object, ...]],
) -> pd.DataFrame:
    positions = {key(row): index for index, (_, row) in enumerate(validated.iterrows())}
    desired = [positions[key(row)] for _, row in source.iterrows()]
    return validated.iloc[desired].reset_index(drop=True)


def _load_object(path: Path) -> dict[str, Any]:
    return _string_object(_load_json(path), str(path))


def _load_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise LiveTypedSourceRevalidationError(
            f"snapshot JSON must be a regular file: {path}"
        )
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveTypedSourceRevalidationError(
            f"cannot decode snapshot JSON: {path}"
        ) from exc


def _string_object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LiveTypedSourceRevalidationError(f"{field} must be a JSON object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _require_exact_fields(payload: dict[str, Any], expected: set[str], field: str) -> None:
    observed = set(payload)
    if observed != expected:
        raise LiveTypedSourceRevalidationError(
            f"{field} fields mismatch; missing={sorted(expected - observed)}, "
            f"unknown={sorted(observed - expected)}"
        )


def _required_text(payload: dict[str, Any], field: str) -> str:
    if field not in payload:
        raise LiveTypedSourceRevalidationError(f"missing field: {field}")
    return _text(payload[field], field)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveTypedSourceRevalidationError(f"{field} must be non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveTypedSourceRevalidationError(f"{field} must be an integer")
    return value


def _required_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise LiveTypedSourceRevalidationError(f"{field} must be a boolean")
    return value


def _required_string_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise LiveTypedSourceRevalidationError(f"{field} must be a JSON array")
    return [_text(item, field) for item in cast(list[object], value)]


def _cell(row: dict[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise LiveTypedSourceRevalidationError(
            f"CSV field is missing or empty: {field}"
        )
    return value


def _aware_datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LiveTypedSourceRevalidationError(
            f"{field} must be an ISO datetime"
        ) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise LiveTypedSourceRevalidationError(f"{field} must be timezone-aware")
    return result


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LiveTypedSourceRevalidationError(f"{field} must be an ISO date") from exc


def _bool(value: str, field: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise LiveTypedSourceRevalidationError(f"{field} must be True or False")


def _integer(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise LiveTypedSourceRevalidationError(f"{field} must be an integer") from exc


def _float(value: str, field: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise LiveTypedSourceRevalidationError(f"{field} must be a float") from exc


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return _float(value.strip(), "optional feature")


__all__ = [
    "LiveTypedSourceRevalidationError",
    "revalidate_market_snapshot",
    "revalidate_research_snapshot",
]
