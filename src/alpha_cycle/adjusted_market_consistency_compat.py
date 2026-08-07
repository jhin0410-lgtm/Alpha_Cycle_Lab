"""Adjusted-price compatibility for cross-provider market consistency.

The original consistency engine predates the adjusted-price market contract and
therefore rejected any adjusted TossInvest or Kiwoom snapshot.  This module keeps
that engine's immutable-result and integrity layers intact while replacing only
source loading, historical-basis comparison, and scope classification for the
lifetime of one guarded consistency run.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from alpha_cycle import market_consistency_cli as core
from alpha_cycle import market_consistency_runner_cli as runner

BASIS_MISMATCH_PREFIX = "historical adjustment basis mismatch:"


def _strict_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise core.ConsistencyError(f"{field} must be a JSON boolean")
    return value


def _safe_evidence_file(directory: Path, raw_name: object, *, field: str) -> Path:
    name = str(raw_name).strip()
    if not name or Path(name).name != name:
        raise core.ConsistencyError(f"invalid evidence filename: {field}")
    path = (directory / name).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise core.ConsistencyError(f"evidence path escapes directory: {field}") from exc
    if not path.is_file():
        raise core.ConsistencyError(f"evidence file is missing: {field}")
    return path


def _load_toss(directory: Path) -> core.SnapshotEvidence:
    manifest = core._load_json(directory / "manifest.json")
    if manifest.get("provider") != core.TOSS_PROVIDER:
        raise core.ConsistencyError("Toss snapshot provider is not tossinvest-readonly")
    if manifest.get("interval") != "1d":
        raise core.ConsistencyError("Toss snapshot interval is not 1d")
    adjusted = _strict_bool(manifest.get("adjusted"), field="Toss adjusted")
    if core._boolean(
        manifest.get("order_api_enabled"),
        field="Toss order_api_enabled",
    ):
        raise core.ConsistencyError("Toss snapshot unexpectedly enables order API")
    core._validate_symbols(manifest, provider="TossInvest")
    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if not snapshot_id:
        raise core.ConsistencyError("Toss manifest has no snapshot_id")
    captured_at = core._parse_datetime(
        manifest.get("captured_at"),
        field="Toss captured_at",
    )

    prices: dict[str, core.Decimal] = {}
    for row in core._read_csv(directory / "prices.csv"):
        core._require_fields(
            row,
            ("symbol", "timestamp", "last_price", "currency"),
            source="prices.csv",
        )
        symbol = row["symbol"].strip()
        if row["currency"].strip().upper() != "KRW":
            raise core.ConsistencyError(f"Toss currency is not KRW for {symbol}")
        core._parse_datetime(row["timestamp"], field=f"Toss price timestamp {symbol}")
        prices[symbol] = core._decimal(
            row["last_price"], field=f"Toss last_price {symbol}"
        )

    candles: dict[tuple[str, date], core.CandleValues] = {}
    required = (
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "interval",
        "adjusted",
    )
    for row in core._read_csv(directory / "candles.csv"):
        core._require_fields(row, required, source="candles.csv")
        symbol = row["symbol"].strip()
        if row["currency"].strip().upper() != "KRW":
            raise core.ConsistencyError(f"Toss candle currency is not KRW for {symbol}")
        if row["interval"].strip() != "1d":
            raise core.ConsistencyError(f"Toss candle interval is not 1d for {symbol}")
        row_adjusted = core._boolean(
            row["adjusted"], field=f"Toss adjusted {symbol}"
        )
        if row_adjusted is not adjusted:
            raise core.ConsistencyError(
                f"Toss candle adjustment basis differs from manifest for {symbol}"
            )
        timestamp = core._parse_datetime(
            row["timestamp"], field=f"Toss candle timestamp {symbol}"
        )
        key = (symbol, timestamp.astimezone(core.KOREA_TZ).date())
        if key in candles:
            raise core.ConsistencyError(f"duplicate Toss candle for {key}")
        candles[key] = (
            core._decimal(row["open"], field="Toss open"),
            core._decimal(row["high"], field="Toss high"),
            core._decimal(row["low"], field="Toss low"),
            core._decimal(row["close"], field="Toss close"),
            core._decimal(row["volume"], field="Toss volume"),
        )
    if tuple(sorted(prices)) != core.EXPECTED_SYMBOLS:
        raise core.ConsistencyError("Toss prices.csv symbol set is incomplete")
    return core.SnapshotEvidence(
        provider=core.TOSS_PROVIDER,
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        directory=directory,
        prices=prices,
        candles=candles,
    )


def _adjustment_keys(directory: Path, manifest: Mapping[str, object]) -> set[tuple[str, str]]:
    adjustment_path = _safe_evidence_file(
        directory,
        manifest.get("adjustment_evidence_file"),
        field="adjustment_evidence_file",
    )
    keys: set[tuple[str, str]] = set()
    for row in core._read_csv(adjustment_path):
        ticker = row.get("ticker", "").strip().zfill(6)
        day = row.get("date", "").strip()
        key = (ticker, day)
        if key in keys:
            raise core.ConsistencyError(f"duplicate Kiwoom adjustment evidence: {key}")
        if (
            row.get("requested_price_basis", "").strip() != "adjusted"
            or row.get("adjustment_request_value", "").strip() != "1"
        ):
            raise core.ConsistencyError(
                f"unexpected Kiwoom adjustment request evidence: {key}"
            )
        keys.add(key)
    return keys


def _load_kiwoom(directory: Path) -> core.SnapshotEvidence:
    manifest = core._load_json(directory / "manifest.json")
    if (
        manifest.get("status") != "completed"
        or manifest.get("provider") != core.KIWOOM_PROVIDER
    ):
        raise core.ConsistencyError("Kiwoom manifest is not a completed export")
    adjusted = _strict_bool(
        manifest.get("adjusted_prices"), field="Kiwoom adjusted_prices"
    )
    if adjusted:
        if manifest.get("price_basis") != "adjusted":
            raise core.ConsistencyError("Kiwoom adjusted manifest has wrong price_basis")
        if str(manifest.get("adjustment_request_value", "")).strip() != "1":
            raise core.ConsistencyError(
                "Kiwoom adjusted manifest did not record 수정주가구분=1"
            )
        adjustment_keys = _adjustment_keys(directory, manifest)
    else:
        adjustment_keys = set()

    for field in ("account_api_enabled", "order_api_enabled"):
        if core._boolean(manifest.get(field), field=f"Kiwoom {field}"):
            raise core.ConsistencyError(f"Kiwoom manifest unexpectedly enables {field}")
    core._validate_symbols(manifest, provider="Kiwoom")
    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if not snapshot_id:
        raise core.ConsistencyError("Kiwoom manifest has no snapshot_id")
    captured_at = core._parse_datetime(
        manifest.get("captured_at_utc"), field="Kiwoom captured_at_utc"
    )

    prices: dict[str, core.Decimal] = {}
    for row in core._read_csv(directory / "quotes.csv"):
        core._require_fields(row, ("ticker", "current_price"), source="quotes.csv")
        ticker = row["ticker"].strip()
        prices[ticker] = core._decimal(
            row["current_price"], field=f"Kiwoom current_price {ticker}"
        )

    candles: dict[tuple[str, date], core.CandleValues] = {}
    seen_bar_keys: set[tuple[str, str]] = set()
    required = (
        "ticker",
        "date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "adjusted",
    )
    for row in core._read_csv(directory / "daily_bars.csv"):
        core._require_fields(row, required, source="daily_bars.csv")
        ticker = row["ticker"].strip()
        row_adjusted = core._boolean(
            row["adjusted"], field=f"Kiwoom adjusted {ticker}"
        )
        if row_adjusted is not adjusted:
            raise core.ConsistencyError(
                f"Kiwoom daily-bar adjustment basis differs from manifest for {ticker}"
            )
        raw_day = row["date"].strip()
        try:
            candle_date = datetime.strptime(raw_day, "%Y%m%d").date()
        except ValueError as exc:
            raise core.ConsistencyError(f"invalid Kiwoom daily date: {raw_day}") from exc
        evidence_key = (ticker.zfill(6), raw_day)
        if evidence_key in seen_bar_keys:
            raise core.ConsistencyError(f"duplicate Kiwoom daily bar for {evidence_key}")
        seen_bar_keys.add(evidence_key)
        key = (ticker, candle_date)
        candles[key] = (
            core._decimal(row["open_price"], field="Kiwoom open"),
            core._decimal(row["high_price"], field="Kiwoom high"),
            core._decimal(row["low_price"], field="Kiwoom low"),
            core._decimal(row["close_price"], field="Kiwoom close"),
            core._decimal(row["volume"], field="Kiwoom volume"),
        )
    if adjusted and seen_bar_keys != adjustment_keys:
        raise core.ConsistencyError(
            "Kiwoom adjustment evidence does not match the daily-bar universe"
        )
    if tuple(sorted(prices)) != core.EXPECTED_SYMBOLS:
        raise core.ConsistencyError("Kiwoom quotes.csv symbol set is incomplete")
    return core.SnapshotEvidence(
        provider=core.KIWOOM_PROVIDER,
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        directory=directory,
        prices=prices,
        candles=candles,
    )


def _basis_from_evidence(evidence: core.SnapshotEvidence) -> bool:
    manifest = core._load_json(evidence.directory / "manifest.json")
    field = "adjusted" if evidence.provider == core.TOSS_PROVIDER else "adjusted_prices"
    return _strict_bool(manifest.get(field), field=f"{evidence.provider} {field}")


def _compare_daily(
    original: Any,
    toss: core.SnapshotEvidence,
    kiwoom: core.SnapshotEvidence,
    *,
    required_days: int,
    price_tolerance_won: core.Decimal,
) -> tuple[list[core.DailyComparison], tuple[str, ...], list[str], list[str]]:
    toss_adjusted = _basis_from_evidence(toss)
    kiwoom_adjusted = _basis_from_evidence(kiwoom)
    if toss_adjusted is not kiwoom_adjusted:
        failure = (
            f"{BASIS_MISMATCH_PREFIX} TossInvest adjusted={str(toss_adjusted).lower()}, "
            f"Kiwoom adjusted={str(kiwoom_adjusted).lower()}"
        )
        warning = (
            "historical OHLC not compared because provider adjustment bases differ"
        )
        return [], (), [failure], [warning]
    return original(
        toss,
        kiwoom,
        required_days=required_days,
        price_tolerance_won=price_tolerance_won,
    )


def _source_scope_contracts(result: core.ConsistencyResult) -> tuple[str, str, bool]:
    toss_manifest = runner._load_json(Path(result.toss_directory) / "manifest.json")
    kiwoom_manifest = runner._load_json(Path(result.kiwoom_directory) / "manifest.json")
    if toss_manifest.get("provider") != core.TOSS_PROVIDER:
        raise runner.ScopeAssessmentError("unexpected TossInvest provider contract")
    if kiwoom_manifest.get("provider") != core.KIWOOM_PROVIDER:
        raise runner.ScopeAssessmentError("unexpected Kiwoom provider contract")
    if str(kiwoom_manifest.get("daily_tr_code", "")).strip() != runner.KIWOOM_DAILY_TR_CODE:
        return "unknown", "unknown", False

    toss_adjusted = _strict_bool(toss_manifest.get("adjusted"), field="Toss adjusted")
    kiwoom_adjusted = _strict_bool(
        kiwoom_manifest.get("adjusted_prices"), field="Kiwoom adjusted_prices"
    )
    if toss_adjusted is not kiwoom_adjusted:
        return (
            f"basis:{'adjusted' if toss_adjusted else 'unadjusted'}",
            f"basis:{'adjusted' if kiwoom_adjusted else 'unadjusted'}",
            False,
        )

    toss_scope = str(
        toss_manifest.get("historical_market_scope", "provider_unspecified_domestic_scope")
    ).strip()
    kiwoom_scope = str(
        kiwoom_manifest.get("historical_market_scope", "krx_opt10081")
    ).strip()
    explicitly_equal = (
        "historical_market_scope" in toss_manifest
        and "historical_market_scope" in kiwoom_manifest
        and toss_scope == kiwoom_scope
    )
    return toss_scope, kiwoom_scope, not explicitly_equal


def _classify_scope(
    original: Any,
    result: core.ConsistencyResult,
    evidence: tuple[runner.SymbolScopeEvidence, ...],
) -> runner.ScopeClassification:
    mismatch = next(
        (failure for failure in result.failures if failure.startswith(BASIS_MISMATCH_PREFIX)),
        None,
    )
    if mismatch is None:
        return original(result, evidence)

    toss_scope, kiwoom_scope, _ = _source_scope_contracts(result)
    return runner.ScopeClassification(
        status="blocked_adjustment_basis_mismatch",
        classification="adjustment_basis_mismatch",
        scope_incompatible_symbols=(),
        control_symbols_verified=(),
        scope_incompatible_row_count=0,
        comparable_scope_price_conflict_count=0,
        historical_scope_status="not_comparable",
        rationale=(
            mismatch,
            "Historical OHLC values were not compared across different adjustment bases.",
            "The pinned Toss snapshot may remain primary evidence, but cross-provider "
            "historical and reference-price certification stay disabled.",
        ),
        toss_historical_market_scope=toss_scope,
        kiwoom_historical_market_scope=kiwoom_scope,
    )


@contextmanager
def adjusted_market_consistency_runtime() -> Iterator[None]:
    """Temporarily install adjusted-aware loaders and classifiers, then restore them."""

    original_load_toss: Any = core._load_toss
    original_load_kiwoom: Any = core._load_kiwoom
    original_compare_daily: Any = core._compare_daily
    original_source_scope: Any = runner._source_scope_contracts
    original_classify: Any = runner._classify_scope

    def compare_daily(
        toss: core.SnapshotEvidence,
        kiwoom: core.SnapshotEvidence,
        *,
        required_days: int,
        price_tolerance_won: core.Decimal,
    ) -> tuple[list[core.DailyComparison], tuple[str, ...], list[str], list[str]]:
        return _compare_daily(
            original_compare_daily,
            toss,
            kiwoom,
            required_days=required_days,
            price_tolerance_won=price_tolerance_won,
        )

    def classify_scope(
        result: core.ConsistencyResult,
        evidence: tuple[runner.SymbolScopeEvidence, ...],
    ) -> runner.ScopeClassification:
        return _classify_scope(original_classify, result, evidence)

    core._load_toss = _load_toss
    core._load_kiwoom = _load_kiwoom
    core._compare_daily = compare_daily
    runner._source_scope_contracts = _source_scope_contracts
    runner._classify_scope = classify_scope
    try:
        yield
    finally:
        core._load_toss = original_load_toss
        core._load_kiwoom = original_load_kiwoom
        core._compare_daily = original_compare_daily
        runner._source_scope_contracts = original_source_scope
        runner._classify_scope = original_classify


__all__ = [
    "BASIS_MISMATCH_PREFIX",
    "adjusted_market_consistency_runtime",
]
