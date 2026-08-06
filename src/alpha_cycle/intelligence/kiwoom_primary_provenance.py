"""Content-addressed single-provider provenance for a Kiwoom-primary decision run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.kiwoom_primary_market import PROVIDER
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)


@dataclass(frozen=True)
class KiwoomPrimaryProvenance(MarketConsistencyProvenance):
    """Explicitly record that no independent market provider certified the prices."""

    @property
    def mode(self) -> str:
        return "kiwoom_primary_only"


def _object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): item for key, item in value.items()}


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_kiwoom_primary_provenance(
    market_directory: str | Path,
    *,
    decision_symbols: tuple[str, ...],
) -> KiwoomPrimaryProvenance:
    """Validate a standard market snapshot backed by one immutable Kiwoom export."""

    market_root = Path(market_directory).resolve(strict=True)
    manifest_path = market_root / "manifest.json"
    raw_prices_path = market_root / "raw_prices.json"
    manifest = _object(manifest_path)
    raw_prices = _object(raw_prices_path)
    if manifest.get("provider") != PROVIDER:
        raise ValueError("market snapshot is not a Kiwoom-primary snapshot")
    market_snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if len(market_snapshot_id) != 64:
        raise ValueError("Kiwoom-primary market snapshot_id is invalid")
    source_snapshot_id = str(raw_prices.get("source_snapshot_id", "")).strip()
    if len(source_snapshot_id) != 64:
        raise ValueError("Kiwoom source snapshot_id is invalid")
    source_manifest_path = Path(str(raw_prices.get("source_manifest_path", "")).strip())
    if not source_manifest_path.is_absolute():
        source_manifest_path = Path.cwd() / source_manifest_path
    source_manifest_path = source_manifest_path.resolve(strict=True)
    source_manifest = _object(source_manifest_path)
    if source_manifest.get("provider") != "kiwoom_openapi_plus":
        raise ValueError("unexpected Kiwoom source provider")
    if source_manifest.get("status") != "completed":
        raise ValueError("Kiwoom source export is not completed")
    if source_manifest.get("snapshot_id") != source_snapshot_id:
        raise ValueError("Kiwoom source snapshot_id does not match")
    if bool(source_manifest.get("account_api_enabled")):
        raise ValueError("Kiwoom source enabled account API")
    if bool(source_manifest.get("order_api_enabled")):
        raise ValueError("Kiwoom source enabled order API")

    source_symbols = tuple(
        sorted(str(item).strip().zfill(6) for item in cast(list[object], source_manifest.get("symbols", [])))
    )
    normalized_decisions = tuple(sorted(set(item.strip().zfill(6) for item in decision_symbols)))
    if not normalized_decisions or not set(normalized_decisions).issubset(source_symbols):
        raise ValueError("decision symbols are not covered by Kiwoom source evidence")

    checked_at = str(source_manifest.get("captured_at_utc", "")).strip()
    base_payload: dict[str, object] = {
        "mode": "kiwoom_primary_only",
        "market_snapshot_id": market_snapshot_id,
        "kiwoom_snapshot_id": source_snapshot_id,
        "checked_at_utc": checked_at,
        "expected_symbols": list(source_symbols),
        "decision_symbols": list(normalized_decisions),
        "source_manifest_path": str(source_manifest_path),
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    result_id = _digest({**base_payload, "kind": "single_provider_result"})
    assessment_id = _digest({**base_payload, "kind": "single_provider_assessment"})
    warnings = (
        "kiwoom_primary_only_tossinvest_unavailable",
        "historical_ohlc_not_cross_provider_certified",
        "reference_price_not_cross_provider_certified",
        "single_provider_market_scope_user_selected_login_server",
        "automatic_provider_substitution_disabled",
        "account_api_disabled",
        "order_api_disabled",
    )
    return KiwoomPrimaryProvenance(
        assessment_id=assessment_id,
        result_id=result_id,
        checked_at_utc=checked_at,
        raw_status="single_provider_read_only",
        classification="kiwoom_primary_tossinvest_ip_blocked",
        historical_scope_status="single_provider_unverified",
        market_snapshot_id=market_snapshot_id,
        kiwoom_snapshot_id=source_snapshot_id,
        expected_symbols=source_symbols,
        live_quote_status="single_provider_only",
        historical_verified=False,
        live_price_certified=False,
        decision_integration_eligible=False,
        assessment_path=str(source_manifest_path),
        result_path=str(source_manifest_path),
        warnings=warnings,
    )


__all__ = ["KiwoomPrimaryProvenance", "load_kiwoom_primary_provenance"]
