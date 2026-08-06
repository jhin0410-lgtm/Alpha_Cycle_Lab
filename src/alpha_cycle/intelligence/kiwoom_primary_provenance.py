"""Content-addressed provenance for a Kiwoom-only read-only market failover."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.kiwoom_primary_market import (
    EXPECTED_SYMBOLS,
    PRIMARY_PROVIDER,
    KiwoomPrimaryMarketError,
    load_kiwoom_primary_manifest,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)

RESULT_SCHEMA_VERSION = "1.0"
ASSESSMENT_SCHEMA_VERSION = "1.0"
CLASSIFICATION = "kiwoom_readonly_primary_due_toss_ip_allowlist"
HISTORICAL_SCOPE_STATUS = "single_provider_not_cross_certified"
LIVE_QUOTE_STATUS = "single_provider_fresh"
PROVENANCE_ROOT_NAME = "primary-market-provenance"
LATEST_POINTER_NAME = "latest_primary_market_provenance.json"
_HEX = frozenset("0123456789abcdef")


class KiwoomPrimaryMarketProvenance(MarketConsistencyProvenance):
    """One fresh Kiwoom snapshot without cross-provider certification."""

    @property
    def mode(self) -> str:
        return "kiwoom_primary_readonly"


@dataclass(frozen=True)
class KiwoomPrimaryMarketGate:
    raw_result_path: Path
    assessment_path: Path
    provenance: KiwoomPrimaryMarketProvenance


def _object(path: Path) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomPrimaryMarketError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KiwoomPrimaryMarketError(f"JSON evidence must be an object: {path}")
    return {str(key): value for key, value in payload.items()}


def _sha256(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(character not in _HEX for character in text):
        raise KiwoomPrimaryMarketError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _canonical_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(payload),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                dict(payload),
                handle,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KiwoomPrimaryMarketError("market symbols must be a list")
    symbols = tuple(sorted(str(item).strip().zfill(6) for item in value))
    if symbols != EXPECTED_SYMBOLS:
        raise KiwoomPrimaryMarketError("market snapshot does not cover the fixed universe")
    return symbols


def _required_symbols(values: Iterable[str]) -> tuple[str, ...]:
    symbols = tuple(sorted({str(value).strip().zfill(6) for value in values}))
    if not symbols or any(len(value) != 6 or not value.isdigit() for value in symbols):
        raise KiwoomPrimaryMarketError("decision_symbols contains an invalid ticker")
    if not set(symbols).issubset(EXPECTED_SYMBOLS):
        raise KiwoomPrimaryMarketError("Kiwoom primary evidence misses decision symbols")
    return symbols


def _safe_false(payload: Mapping[str, object], field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, bool) or value:
        raise KiwoomPrimaryMarketError(f"{field} must be explicit false")


def _validate_source_payload(
    output_root: Path,
    market_directory: Path,
    market_snapshot_id: str,
) -> tuple[str, datetime, tuple[str, ...], dict[str, object]]:
    manifest = load_kiwoom_primary_manifest(
        market_directory,
        max_age_minutes=30,
    )
    if str(manifest.get("provider", "")) != PRIMARY_PROVIDER:
        raise KiwoomPrimaryMarketError("unexpected primary market provider")
    if _sha256(manifest.get("snapshot_id"), "market snapshot_id") != market_snapshot_id:
        raise KiwoomPrimaryMarketError("market snapshot ID changed before provenance binding")
    symbols = _symbols(manifest.get("symbols"))
    captured_at = datetime.fromisoformat(str(manifest.get("captured_at", "")))
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise KiwoomPrimaryMarketError("market captured_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)

    source = _object(market_directory / "raw_prices.json")
    source_id = _sha256(source.get("source_snapshot_id"), "source snapshot_id")
    source_directory = Path(str(source.get("source_export_directory", "")))
    source_manifest = Path(str(source.get("source_manifest_path", "")))
    if not source_directory.is_absolute():
        source_directory = Path.cwd() / source_directory
    if not source_manifest.is_absolute():
        source_manifest = Path.cwd() / source_manifest
    try:
        source_directory = source_directory.resolve(strict=True)
        source_manifest = source_manifest.resolve(strict=True)
        source_directory.relative_to(output_root.resolve(strict=True))
        source_manifest.relative_to(source_directory)
    except (OSError, ValueError) as exc:
        raise KiwoomPrimaryMarketError("Kiwoom source evidence escapes the output root") from exc
    if source_manifest.parent != source_directory or not source_manifest.is_file():
        raise KiwoomPrimaryMarketError("Kiwoom source manifest linkage is invalid")
    original_manifest = _object(source_manifest)
    if _sha256(original_manifest.get("snapshot_id"), "source manifest snapshot_id") != source_id:
        raise KiwoomPrimaryMarketError("source manifest belongs to a different export")
    if str(original_manifest.get("provider", "")) != "kiwoom_openapi_plus":
        raise KiwoomPrimaryMarketError("source manifest provider is invalid")
    for field in (
        "cross_provider_price_certified",
        "automatic_provider_substitution_enabled",
        "account_api_enabled",
        "order_api_enabled",
    ):
        _safe_false(source, field)
    if source.get("fallback_reason") != "tossinvest_ip_allowlist":
        raise KiwoomPrimaryMarketError("source fallback reason is invalid")
    if source.get("read_only_market_failover_used") is not True:
        raise KiwoomPrimaryMarketError("source failover marker is missing")
    return source_id, captured_at, symbols, source


def _existing_matches(directory: Path, result_id: str, assessment_id: str) -> bool:
    try:
        result = _object(directory / "primary_result.json")
        assessment = _object(directory / "primary_assessment.json")
    except KiwoomPrimaryMarketError:
        return False
    return result.get("result_id") == result_id and assessment.get("assessment_id") == assessment_id


def run_kiwoom_primary_market_gate(
    *,
    output_root: str | Path,
    market_directory: str | Path,
    decision_symbols: Iterable[str],
) -> KiwoomPrimaryMarketGate:
    """Validate and bind one fresh Kiwoom-only read-only market snapshot."""

    root = Path(output_root).resolve()
    market_dir = Path(market_directory).resolve(strict=True)
    try:
        market_dir.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise KiwoomPrimaryMarketError("market snapshot escapes the pipeline output root") from exc
    required_symbols = _required_symbols(decision_symbols)
    manifest = _object(market_dir / "manifest.json")
    market_id = _sha256(manifest.get("snapshot_id"), "market snapshot_id")
    source_id, captured_at, symbols, source = _validate_source_payload(
        root,
        market_dir,
        market_id,
    )
    if not set(required_symbols).issubset(symbols):
        raise KiwoomPrimaryMarketError("primary market snapshot misses decision symbols")

    warnings = (
        "market_provider_failover_kiwoom_readonly",
        "tossinvest_unavailable_due_ip_allowlist",
        "single_provider_historical_ohlc_not_cross_certified",
        "single_provider_reference_price_not_cross_certified",
        "account_and_order_apis_disabled",
    )
    result_without_id: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "primary_source_only",
        "provider": PRIMARY_PROVIDER,
        "checked_at_utc": captured_at.isoformat(),
        "market_snapshot_id": market_id,
        "kiwoom_snapshot_id": source_id,
        "expected_symbols": list(symbols),
        "decision_symbols": list(required_symbols),
        "fallback_reason": "tossinvest_ip_allowlist",
        "historical_cross_provider_verified": False,
        "live_price_cross_provider_certified": False,
        "decision_integration_eligible": False,
        "read_only_market_failover_used": True,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "source_manifest_sha256": source.get("source_manifest_sha256"),
        "source_quotes_sha256": source.get("source_quotes_sha256"),
        "source_daily_bars_sha256": source.get("source_daily_bars_sha256"),
        "warnings": list(warnings),
    }
    result_id = _canonical_id(result_without_id)
    provenance_root = root / PROVENANCE_ROOT_NAME
    directory = provenance_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__" + result_id[:12]
    )
    result_path = directory / "primary_result.json"
    assessment_without_id: dict[str, object] = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "status": "primary_source_only",
        "classification": CLASSIFICATION,
        "checked_at_utc": captured_at.isoformat(),
        "raw_result_id": result_id,
        "raw_result_path": str(result_path),
        "provider": PRIMARY_PROVIDER,
        "market_snapshot_id": market_id,
        "kiwoom_snapshot_id": source_id,
        "historical_scope_status": HISTORICAL_SCOPE_STATUS,
        "live_quote_status": LIVE_QUOTE_STATUS,
        "historical_verified": False,
        "live_price_certified": False,
        "decision_integration_eligible": False,
        "read_only_market_failover_used": True,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "warnings": list(warnings),
    }
    assessment_id = _canonical_id(assessment_without_id)
    assessment_path = directory / "primary_assessment.json"
    result = {**result_without_id, "result_id": result_id}
    assessment = {**assessment_without_id, "assessment_id": assessment_id}

    provenance_root.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        if not _existing_matches(directory, result_id, assessment_id):
            raise KiwoomPrimaryMarketError("existing primary provenance directory conflicts")
    else:
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{directory.name}.", suffix=".tmp", dir=provenance_root)
        )
        try:
            _atomic_json(temporary / result_path.name, result)
            _atomic_json(temporary / assessment_path.name, assessment)
            try:
                temporary.rename(directory)
            except OSError:
                if not _existing_matches(directory, result_id, assessment_id):
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    pointer = {
        "status": "primary_source_only",
        "classification": CLASSIFICATION,
        "result_id": result_id,
        "result_path": str(result_path),
        "assessment_id": assessment_id,
        "assessment_path": str(assessment_path),
        "market_snapshot_id": market_id,
        "kiwoom_snapshot_id": source_id,
        "read_only_market_failover_used": True,
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    _atomic_json(root / LATEST_POINTER_NAME, pointer)

    provenance = KiwoomPrimaryMarketProvenance(
        assessment_id=assessment_id,
        result_id=result_id,
        checked_at_utc=captured_at.isoformat(),
        raw_status="primary_source_only",
        classification=CLASSIFICATION,
        historical_scope_status=HISTORICAL_SCOPE_STATUS,
        market_snapshot_id=market_id,
        kiwoom_snapshot_id=source_id,
        expected_symbols=symbols,
        live_quote_status=LIVE_QUOTE_STATUS,
        historical_verified=False,
        live_price_certified=False,
        decision_integration_eligible=False,
        assessment_path=str(assessment_path),
        result_path=str(result_path),
        warnings=warnings,
    )
    return KiwoomPrimaryMarketGate(
        raw_result_path=result_path,
        assessment_path=assessment_path,
        provenance=provenance,
    )


__all__ = [
    "CLASSIFICATION",
    "KiwoomPrimaryMarketGate",
    "KiwoomPrimaryMarketProvenance",
    "run_kiwoom_primary_market_gate",
]
