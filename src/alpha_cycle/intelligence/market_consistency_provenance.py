"""Validated market-consistency provenance for investment decisions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from alpha_cycle.market_consistency_cli import _result_id
from alpha_cycle.market_consistency_runner_cli import _assessment_id

_HEX = frozenset("0123456789abcdef")
_ALLOWED_RAW_STATUSES = frozenset({"passed", "passed_historical_only"})
_REQUIRED_CLASSIFICATION = "equivalent_scope_observed"
_REQUIRED_SCOPE_STATUS = "comparable"


@dataclass(frozen=True)
class MarketConsistencyProvenance:
    """Content-addressed cross-provider evidence linked to one market snapshot."""

    assessment_id: str
    result_id: str
    checked_at_utc: str
    raw_status: str
    classification: str
    historical_scope_status: str
    market_snapshot_id: str
    kiwoom_snapshot_id: str
    expected_symbols: tuple[str, ...]
    live_quote_status: str
    historical_verified: bool
    live_price_certified: bool
    decision_integration_eligible: bool
    assessment_path: str
    result_path: str
    warnings: tuple[str, ...]

    @property
    def mode(self) -> str:
        return "live_certified" if self.live_price_certified else "historical_only"

    def payload(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "result_id": self.result_id,
            "checked_at_utc": self.checked_at_utc,
            "raw_status": self.raw_status,
            "classification": self.classification,
            "historical_scope_status": self.historical_scope_status,
            "market_snapshot_id": self.market_snapshot_id,
            "kiwoom_snapshot_id": self.kiwoom_snapshot_id,
            "expected_symbols": list(self.expected_symbols),
            "live_quote_status": self.live_quote_status,
            "historical_verified": self.historical_verified,
            "live_price_certified": self.live_price_certified,
            "decision_integration_eligible": self.decision_integration_eligible,
            "mode": self.mode,
            "assessment_path": self.assessment_path,
            "result_path": self.result_path,
            "warnings": list(self.warnings),
        }


def _object(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(Mapping[str, object], payload)


def _sha256(value: object, field: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in _HEX for character in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return text


def _boolean(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _safe_boundary(payload: Mapping[str, object], source: str) -> None:
    for field in (
        "automatic_provider_substitution_enabled",
        "account_api_enabled",
        "order_api_enabled",
    ):
        if _boolean(payload, field):
            raise ValueError(f"{source} cannot enable {field}")


def _linked_file(root: Path, value: object, field: str) -> Path:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} is missing")
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{field} does not resolve to a file: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"{field} is not a file: {resolved}")
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"{field} escapes the consistency root: {resolved}") from exc
    return resolved


def _same_path(left: object, right: Path, field: str) -> None:
    candidate = Path(str(left))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.resolve() != right.resolve():
        raise ValueError(f"{field} points to a different artifact")


def _recomputed_id(
    payload: Mapping[str, object],
    *,
    field: str,
    calculator: object,
) -> str:
    without_id = {key: value for key, value in payload.items() if key != field}
    if calculator is _result_id:
        computed = _result_id(without_id)
    else:
        computed = _assessment_id(without_id)
    stored = _sha256(payload.get(field), field)
    if stored != computed:
        raise ValueError(f"{field} does not match linked artifact content")
    return stored


def _symbols(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized = tuple(sorted(str(item).strip().zfill(6) for item in value))
    if not normalized or any(not item.isdigit() or len(item) != 6 for item in normalized):
        raise ValueError(f"{field} contains an invalid ticker")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} contains duplicate tickers")
    return normalized


def _assessment_symbols(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("assessment symbols must be a list")
    tickers: list[str] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("assessment symbol evidence must contain objects")
        ticker = str(row.get("ticker", "")).strip().zfill(6)
        if len(ticker) != 6 or not ticker.isdigit():
            raise ValueError("assessment symbol evidence has an invalid ticker")
        tickers.append(ticker)
    result = tuple(sorted(tickers))
    if len(set(result)) != len(result):
        raise ValueError("assessment symbol evidence contains duplicate tickers")
    return result


def _zero(payload: Mapping[str, object], field: str) -> None:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 0:
        raise ValueError(f"{field} must be zero")


def _integer(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def load_market_consistency_provenance(
    root: str | Path,
    *,
    market_snapshot_id: str,
    decision_symbols: Iterable[str],
) -> MarketConsistencyProvenance:
    """Load and verify linked raw and assessed cross-provider evidence.

    Only equivalent-scope evidence is accepted. A fully passed result certifies the
    current reference price. A historical-only result certifies completed-session
    OHLC evidence while keeping the current reference price uncertified.
    """

    consistency_root = Path(root).resolve(strict=True)
    if not consistency_root.is_dir():
        raise ValueError(f"Consistency root is not a directory: {consistency_root}")
    market_id = _sha256(market_snapshot_id, "market_snapshot_id")
    required_symbols = tuple(
        sorted({str(item).strip().zfill(6) for item in decision_symbols})
    )
    if not required_symbols:
        raise ValueError("decision_symbols cannot be empty")

    raw_pointer_path = consistency_root / "latest_market_consistency.json"
    assessment_pointer_path = consistency_root / "latest_market_scope_assessment.json"
    raw_pointer = _object(raw_pointer_path)
    assessment_pointer = _object(assessment_pointer_path)
    _safe_boundary(raw_pointer, "raw pointer")
    _safe_boundary(assessment_pointer, "assessment pointer")

    if str(raw_pointer.get("assessment_status", "")) != "completed":
        raise ValueError("Market consistency assessment is not complete")
    result_path = _linked_file(
        consistency_root,
        raw_pointer.get("result_path"),
        "result_path",
    )
    assessment_path = _linked_file(
        consistency_root,
        raw_pointer.get("assessment_path"),
        "assessment_path",
    )
    _same_path(assessment_pointer.get("assessment_path"), assessment_path, "assessment pointer")
    _same_path(assessment_pointer.get("raw_result_path"), result_path, "raw result pointer")

    raw = _object(result_path)
    assessment = _object(assessment_path)
    _safe_boundary(raw, "raw result")
    _safe_boundary(assessment, "assessment")
    result_id = _recomputed_id(
        raw,
        field="result_id",
        calculator=_result_id,
    )
    assessment_id = _recomputed_id(
        assessment,
        field="assessment_id",
        calculator=_assessment_id,
    )

    if _sha256(raw_pointer.get("result_id"), "pointer result_id") != result_id:
        raise ValueError("Raw pointer result_id does not match the linked result")
    if _sha256(raw_pointer.get("assessment_id"), "pointer assessment_id") != assessment_id:
        raise ValueError("Raw pointer assessment_id does not match the linked assessment")
    if _sha256(assessment_pointer.get("assessment_id"), "assessment pointer id") != assessment_id:
        raise ValueError("Assessment pointer does not match the linked assessment")
    if _sha256(assessment.get("raw_result_id"), "assessment raw_result_id") != result_id:
        raise ValueError("Assessment is linked to a different raw result")
    _same_path(assessment.get("raw_result_path"), result_path, "assessment raw_result_path")

    raw_status = str(raw.get("status", ""))
    if raw_status not in _ALLOWED_RAW_STATUSES:
        raise ValueError(f"Raw market consistency status blocks decisions: {raw_status}")
    if str(assessment.get("raw_status", "")) != raw_status:
        raise ValueError("Assessment raw_status does not match the raw result")
    if str(assessment.get("status", "")) != raw_status:
        raise ValueError("Assessment status does not match the raw result")
    classification = str(assessment.get("classification", ""))
    if classification != _REQUIRED_CLASSIFICATION:
        raise ValueError(f"Market scope classification blocks decisions: {classification}")
    if str(raw_pointer.get("classification", "")) != classification:
        raise ValueError("Raw pointer classification does not match the assessment")
    if str(assessment_pointer.get("classification", "")) != classification:
        raise ValueError("Assessment pointer classification does not match")
    historical_scope_status = str(assessment.get("historical_scope_status", ""))
    if historical_scope_status != _REQUIRED_SCOPE_STATUS:
        raise ValueError(
            "Historical market scope is not comparable: " + historical_scope_status
        )

    if _sha256(raw.get("toss_snapshot_id"), "toss_snapshot_id") != market_id:
        raise ValueError("Consistency evidence is linked to a different market snapshot")
    kiwoom_id = _sha256(raw.get("kiwoom_snapshot_id"), "kiwoom_snapshot_id")
    expected_symbols = _symbols(raw.get("expected_symbols"), "expected_symbols")
    if not set(required_symbols).issubset(expected_symbols):
        raise ValueError(
            "Consistency evidence is missing decision symbols: "
            + ",".join(sorted(set(required_symbols) - set(expected_symbols)))
        )
    if _assessment_symbols(assessment.get("symbols")) != expected_symbols:
        raise ValueError("Assessment symbol evidence differs from the raw result")

    for payload, fields in (
        (raw, ("historical_price_conflict_count",)),
        (
            assessment,
            (
                "raw_price_difference_count",
                "tolerance_conflict_count",
                "comparable_scope_price_conflict_count",
                "scope_incompatible_row_count",
            ),
        ),
    ):
        for field in fields:
            _zero(payload, field)

    checked_at = str(raw.get("checked_at_utc", ""))
    parsed_checked_at = datetime.fromisoformat(checked_at)
    if parsed_checked_at.tzinfo is None or parsed_checked_at.utcoffset() is None:
        raise ValueError("checked_at_utc must be timezone-aware")
    if str(assessment.get("checked_at_utc", "")) != checked_at:
        raise ValueError("Assessment checked_at_utc does not match the raw result")

    live_quote_status = str(raw.get("live_quote_status", ""))
    raw_eligible = _boolean(raw, "decision_integration_eligible")
    assessment_eligible = _boolean(assessment, "decision_integration_eligible")
    raw_pointer_eligible = _boolean(raw_pointer, "decision_integration_eligible")
    assessment_pointer_eligible = _boolean(
        assessment_pointer,
        "decision_integration_eligible",
    )
    if len({raw_pointer_eligible, assessment_pointer_eligible, assessment_eligible}) != 1:
        raise ValueError("Market consistency eligibility pointers disagree")

    live_certified = raw_status == "passed"
    if live_certified:
        if live_quote_status != "passed":
            raise ValueError("A passed result must have passed live quotes")
        if not raw_eligible or not assessment_eligible:
            raise ValueError("Passed live evidence is not marked integration-eligible")
        if _integer(raw, "live_quote_comparable_count") != len(expected_symbols):
            raise ValueError("Live comparable count does not cover all expected symbols")
        _zero(raw, "live_quote_conflict_count")
    else:
        if live_quote_status != "not_comparable":
            raise ValueError("Historical-only evidence must mark live quotes not comparable")
        if raw_eligible or assessment_eligible:
            raise ValueError("Historical-only evidence cannot certify live integration")
        _zero(raw, "live_quote_comparable_count")
        _zero(raw, "live_quote_conflict_count")

    rationale = assessment.get("rationale", [])
    raw_warnings = raw.get("warnings", [])
    if not isinstance(rationale, list) or not isinstance(raw_warnings, list):
        raise ValueError("Consistency warnings and rationale must be lists")
    warnings = tuple(
        dict.fromkeys(
            [
                *(str(item) for item in raw_warnings),
                *(str(item) for item in rationale),
            ]
        )
    )
    return MarketConsistencyProvenance(
        assessment_id=assessment_id,
        result_id=result_id,
        checked_at_utc=checked_at,
        raw_status=raw_status,
        classification=classification,
        historical_scope_status=historical_scope_status,
        market_snapshot_id=market_id,
        kiwoom_snapshot_id=kiwoom_id,
        expected_symbols=expected_symbols,
        live_quote_status=live_quote_status,
        historical_verified=True,
        live_price_certified=live_certified,
        decision_integration_eligible=assessment_eligible,
        assessment_path=str(assessment_path),
        result_path=str(result_path),
        warnings=warnings,
    )


__all__ = [
    "MarketConsistencyProvenance",
    "load_market_consistency_provenance",
]
