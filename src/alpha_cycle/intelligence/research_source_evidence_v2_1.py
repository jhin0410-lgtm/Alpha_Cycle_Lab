"""Independent source artifacts for Decision System v2.1 derived evidence.

The package assembler must not trust a derived valuation or expectation envelope merely because
that envelope is internally self-consistent.  This module defines immutable source artifacts that
sit on the other side of that trust boundary:

* ``ValuationSourceSnapshot`` freezes the exact Research/Market files used by valuation together
  with the provider-derived share, security-mapping and financial-history inputs.  A valuation can
  therefore be reconstructed without consulting its own derived CSVs.
* ``CertifiedConsensusSourceSnapshot`` is the authority for a certified market-consensus row.  The
  certification semantics are emitted by this source contract rather than copied from an
  ``ExpectationStateSnapshot``.

KIS expectation artifacts are deliberately excluded from the certified-consensus contract.  The
existing KIS acquisition/normalization chain is explicitly non-certified and must remain so until a
separate provider-specific certification contract is implemented.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
)
from alpha_cycle.intelligence.valuation import (
    ValuationEvidenceSnapshot,
    _load_prices,
    _records,
    _valuation_metrics,
)
from alpha_cycle.research_package_integrity_v2_1 import require_trusted_artifact_root

VALUATION_SOURCE_SCHEMA_VERSION = 1
CERTIFIED_CONSENSUS_SOURCE_SCHEMA_VERSION = 1
VALUATION_SOURCE_REPOSITORY = "valuation_source"
CERTIFIED_CONSENSUS_SOURCE_REPOSITORY = "certified_expectation_source"
_DYNAMIC_SECURITY_COLUMNS = {
    "price",
    "price_timestamp",
    "security_market_value",
    "priced",
}


class ResearchSourceEvidenceError(ValueError):
    """Raised when a persisted source artifact violates its trust contract."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _validate_sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("source evidence values must be finite")
        return value
    if isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported source evidence value: {type(value).__name__}")


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _read_json_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResearchSourceEvidenceError(f"JSON object required: {path}")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _require_regular_contained(path: Path, artifact_root: Path) -> None:
    resolved_root = require_trusted_artifact_root(artifact_root)
    if path.is_symlink() or not path.is_file():
        raise ResearchSourceEvidenceError(f"regular source evidence file required: {path}")
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ResearchSourceEvidenceError(f"source evidence escapes artifact root: {path}")


def _snapshot_id_from_manifest(directory: Path) -> str:
    manifest = _read_json_object(directory / "manifest.json")
    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    _validate_sha256(snapshot_id, "snapshot_id")
    return snapshot_id


@dataclass(frozen=True)
class ValuationSourceSnapshot:
    """Immutable source inputs from which valuation evidence is reproducible."""

    captured_at: datetime
    evaluation_date: date
    research_snapshot_id: str
    market_snapshot_id: str
    history_years: int
    research_manifest_sha256: str
    research_raw_opendart_sha256: str
    market_manifest_sha256: str
    market_prices_sha256: str
    shares: pd.DataFrame
    security_inputs: pd.DataFrame
    financial_history: pd.DataFrame
    raw_provider_evidence: object
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        _validate_sha256(self.research_snapshot_id, "research_snapshot_id")
        _validate_sha256(self.market_snapshot_id, "market_snapshot_id")
        for field, value in (
            ("research_manifest_sha256", self.research_manifest_sha256),
            ("research_raw_opendart_sha256", self.research_raw_opendart_sha256),
            ("market_manifest_sha256", self.market_manifest_sha256),
            ("market_prices_sha256", self.market_prices_sha256),
        ):
            _validate_sha256(value, field)
        if self.history_years <= 0:
            raise ValueError("history_years must be positive")
        required_shares = {"ticker", "security_name", "security_class", "issued_shares"}
        if not required_shares.issubset(self.shares.columns):
            raise ValueError("valuation source shares are incomplete")
        required_inputs = required_shares | {"symbol", "mapping_source"}
        if not required_inputs.issubset(self.security_inputs.columns):
            raise ValueError("valuation source security inputs are incomplete")
        if _DYNAMIC_SECURITY_COLUMNS & set(self.security_inputs.columns):
            raise ValueError("valuation source cannot contain derived market-price columns")
        if self.financial_history.empty:
            raise ValueError("valuation source financial history cannot be empty")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": VALUATION_SOURCE_SCHEMA_VERSION,
            "object_type": "valuation_source",
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_snapshot_id": self.research_snapshot_id,
            "market_snapshot_id": self.market_snapshot_id,
            "history_years": self.history_years,
            "research_manifest_sha256": self.research_manifest_sha256,
            "research_raw_opendart_sha256": self.research_raw_opendart_sha256,
            "market_manifest_sha256": self.market_manifest_sha256,
            "market_prices_sha256": self.market_prices_sha256,
            "shares": _frame_records(self.shares),
            "security_inputs": _frame_records(self.security_inputs),
            "financial_history": _frame_records(self.financial_history),
            "raw_provider_evidence": self.raw_provider_evidence,
            "warnings": list(self.warnings),
            "derived_market_values_present": False,
            "decision_score_enabled": False,
            "fair_value_enabled": False,
            "target_price_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.payload_without_id()).encode("utf-8")
        ).hexdigest()


def build_valuation_source_from_evidence(
    evidence: ValuationEvidenceSnapshot,
    *,
    research_snapshot: str | Path,
    market_snapshot: str | Path,
) -> ValuationSourceSnapshot:
    """Freeze independently replayable inputs from one freshly collected valuation candidate."""

    research_dir = Path(research_snapshot)
    market_dir = Path(market_snapshot)
    for directory, label in ((research_dir, "research"), (market_dir, "market")):
        if not directory.is_dir() or not (directory / "manifest.json").is_file():
            raise ValueError(f"{label} snapshot directory is invalid: {directory}")
    if _snapshot_id_from_manifest(research_dir) != evidence.research_snapshot_id:
        raise ValueError("research source does not match valuation evidence")
    if _snapshot_id_from_manifest(market_dir) != evidence.market_snapshot_id:
        raise ValueError("market source does not match valuation evidence")
    raw_opendart = research_dir / "raw_opendart.json"
    prices = market_dir / "prices.csv"
    if not raw_opendart.is_file() or not prices.is_file():
        raise ValueError("valuation upstream source files are incomplete")
    security_inputs = evidence.security_values.drop(
        columns=[
            column
            for column in _DYNAMIC_SECURITY_COLUMNS
            if column in evidence.security_values.columns
        ]
    ).copy()
    return ValuationSourceSnapshot(
        captured_at=evidence.captured_at,
        evaluation_date=evidence.evaluation_date,
        research_snapshot_id=evidence.research_snapshot_id,
        market_snapshot_id=evidence.market_snapshot_id,
        history_years=evidence.history_years,
        research_manifest_sha256=_sha256_file(research_dir / "manifest.json"),
        research_raw_opendart_sha256=_sha256_file(raw_opendart),
        market_manifest_sha256=_sha256_file(market_dir / "manifest.json"),
        market_prices_sha256=_sha256_file(prices),
        shares=evidence.shares.copy(),
        security_inputs=security_inputs,
        financial_history=evidence.financial_history.copy(),
        raw_provider_evidence=evidence.raw_valuation,
        warnings=evidence.warnings,
    )


def _reprice_security_inputs(
    source: ValuationSourceSnapshot,
    market_dir: Path,
) -> pd.DataFrame:
    prices = _load_prices(market_dir)
    price_lookup = prices.set_index("symbol")["last_price"].to_dict()
    timestamp_lookup = prices.set_index("symbol")["timestamp"].to_dict()
    rows: list[dict[str, object]] = []
    for raw in source.security_inputs.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        raw_symbol = row.get("symbol")
        symbol = None if raw_symbol is None or pd.isna(raw_symbol) else str(raw_symbol).zfill(6)
        price_raw = price_lookup.get(symbol) if symbol is not None else None
        price = None if price_raw is None or pd.isna(price_raw) else float(price_raw)
        shares_raw = row.get("issued_shares")
        issued = None if shares_raw is None or pd.isna(shares_raw) else float(shares_raw)
        row.update(
            {
                "symbol": symbol,
                "price": price,
                "price_timestamp": timestamp_lookup.get(symbol) if symbol is not None else None,
                "security_market_value": (
                    price * issued if price is not None and issued is not None else None
                ),
                "priced": price is not None,
            }
        )
        rows.append(row)
    return (
        pd.DataFrame(rows)
        .sort_values(["ticker", "security_class", "security_name"], kind="stable")
        .reset_index(drop=True)
    )


def validate_valuation_source_upstream(
    source: ValuationSourceSnapshot,
    *,
    research_snapshot: str | Path,
    market_snapshot: str | Path,
) -> None:
    """Bind a source capture to the exact persisted Research and Market bytes it names."""

    research_dir = Path(research_snapshot)
    market_dir = Path(market_snapshot)
    if _snapshot_id_from_manifest(research_dir) != source.research_snapshot_id:
        raise ValueError("valuation source research snapshot identity mismatch")
    if _snapshot_id_from_manifest(market_dir) != source.market_snapshot_id:
        raise ValueError("valuation source market snapshot identity mismatch")
    checks = (
        (research_dir / "manifest.json", source.research_manifest_sha256),
        (research_dir / "raw_opendart.json", source.research_raw_opendart_sha256),
        (market_dir / "manifest.json", source.market_manifest_sha256),
        (market_dir / "prices.csv", source.market_prices_sha256),
    )
    for path, expected in checks:
        if not path.is_file() or _sha256_file(path) != expected:
            raise ValueError(f"valuation upstream source bytes changed: {path.name}")


def rebuild_valuation_evidence_from_source(
    source: ValuationSourceSnapshot,
    *,
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    captured_at: datetime,
) -> ValuationEvidenceSnapshot:
    """Rebuild all market-cap and valuation rows without trusting derived valuation CSVs."""

    validate_valuation_source_upstream(
        source,
        research_snapshot=research_snapshot,
        market_snapshot=market_snapshot,
    )
    security_values = _reprice_security_inputs(source, Path(market_snapshot))
    valuation_metrics = _valuation_metrics(security_values, source.financial_history)
    raw = (
        dict(cast(dict[str, object], source.raw_provider_evidence))
        if isinstance(source.raw_provider_evidence, dict)
        else {"provider_evidence": source.raw_provider_evidence}
    )
    raw["source_research_snapshot_id"] = source.research_snapshot_id
    raw["source_market_snapshot_id"] = source.market_snapshot_id
    raw["source_valuation_snapshot_id"] = source.snapshot_id
    return ValuationEvidenceSnapshot(
        captured_at=captured_at,
        evaluation_date=source.evaluation_date,
        research_snapshot_id=source.research_snapshot_id,
        market_snapshot_id=source.market_snapshot_id,
        history_years=source.history_years,
        shares=source.shares.copy(),
        security_values=security_values,
        financial_history=source.financial_history.copy(),
        valuation_metrics=valuation_metrics,
        raw_valuation=raw,
        warnings=source.warnings,
    )


def _valuation_source_manifest(snapshot: ValuationSourceSnapshot) -> dict[str, object]:
    return {
        "schema_version": VALUATION_SOURCE_SCHEMA_VERSION,
        "object_type": "valuation_source",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "evaluation_date": snapshot.evaluation_date.isoformat(),
        "research_snapshot_id": snapshot.research_snapshot_id,
        "market_snapshot_id": snapshot.market_snapshot_id,
        "history_years": snapshot.history_years,
        "immutable": True,
        "derived_market_values_present": False,
        "decision_score_enabled": False,
        "fair_value_enabled": False,
        "target_price_enabled": False,
        "automatic_execution_enabled": False,
        "files": ["valuation_source.json"],
    }


def persist_valuation_source(
    snapshot: ValuationSourceSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / VALUATION_SOURCE_REPOSITORY
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    temporary = root / f".{directory.name}.tmp"
    if directory.exists():
        loaded = load_persisted_valuation_source(Path(output_root), snapshot.snapshot_id)
        if loaded != snapshot:
            raise ValueError("existing valuation source conflicts with requested source")
        return directory
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "valuation_source.json").write_text(
            json.dumps(snapshot.payload_without_id(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "manifest.json").write_text(
            json.dumps(_valuation_source_manifest(snapshot), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return directory


def _load_source_envelope(
    artifact_root: Path,
    *,
    repository_name: str,
    snapshot_id: str,
    payload_name: str,
) -> tuple[dict[str, object], dict[str, object], Path] | None:
    resolved_root = require_trusted_artifact_root(artifact_root)
    repository = artifact_root / repository_name
    if not repository.exists():
        return None
    if repository.is_symlink() or not repository.is_dir():
        raise ResearchSourceEvidenceError(f"{repository_name} must be a regular directory")
    resolved_repository = repository.resolve()
    if resolved_repository.parent != resolved_root:
        raise ResearchSourceEvidenceError(f"{repository_name} escapes artifact root")
    matches: list[Path] = []
    for candidate in repository.iterdir():
        if not candidate.name.endswith(f"__{snapshot_id[:12]}"):
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            raise ResearchSourceEvidenceError("source snapshot must be a regular directory")
        if candidate.resolve().parent != resolved_repository:
            raise ResearchSourceEvidenceError("source snapshot escapes repository")
        manifest_path = candidate / "manifest.json"
        payload_path = candidate / payload_name
        _require_regular_contained(manifest_path, artifact_root)
        _require_regular_contained(payload_path, artifact_root)
        manifest = _read_json_object(manifest_path)
        if str(manifest.get("snapshot_id", "")) == snapshot_id:
            matches.append(candidate)
    if len(matches) > 1:
        raise ResearchSourceEvidenceError(f"duplicate {repository_name} source identity")
    if not matches:
        return None
    directory = matches[0]
    return (
        _read_json_object(directory / payload_name),
        _read_json_object(directory / "manifest.json"),
        directory,
    )


def _source_frame(payload: dict[str, object], field: str) -> pd.DataFrame:
    value = payload[field]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be an array of objects")
    return pd.DataFrame(value)


def _source_text(payload: dict[str, object], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value


def load_persisted_valuation_source(
    artifact_root: str | Path,
    snapshot_id: str,
) -> ValuationSourceSnapshot | None:
    root = Path(artifact_root)
    envelope = _load_source_envelope(
        root,
        repository_name=VALUATION_SOURCE_REPOSITORY,
        snapshot_id=snapshot_id,
        payload_name="valuation_source.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        snapshot = ValuationSourceSnapshot(
            captured_at=datetime.fromisoformat(_source_text(payload, "captured_at")),
            evaluation_date=date.fromisoformat(_source_text(payload, "evaluation_date")),
            research_snapshot_id=_source_text(payload, "research_snapshot_id"),
            market_snapshot_id=_source_text(payload, "market_snapshot_id"),
            history_years=int(payload["history_years"]),
            research_manifest_sha256=_source_text(payload, "research_manifest_sha256"),
            research_raw_opendart_sha256=_source_text(payload, "research_raw_opendart_sha256"),
            market_manifest_sha256=_source_text(payload, "market_manifest_sha256"),
            market_prices_sha256=_source_text(payload, "market_prices_sha256"),
            shares=_source_frame(payload, "shares"),
            security_inputs=_source_frame(payload, "security_inputs"),
            financial_history=_source_frame(payload, "financial_history"),
            raw_provider_evidence=payload["raw_provider_evidence"],
            warnings=tuple(str(item) for item in cast(list[object], payload.get("warnings", []))),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_payload = snapshot.payload_without_id()
    expected_manifest = _valuation_source_manifest(snapshot)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if (
        payload != expected_payload
        or manifest != expected_manifest
        or snapshot.snapshot_id != snapshot_id
        or directory.name != f"{timestamp}__{snapshot.snapshot_id[:12]}"
    ):
        return None
    return snapshot


@dataclass(frozen=True)
class CertifiedConsensusSourceSnapshot:
    """Independent provider evidence for exactly one certified consensus observation."""

    captured_at: datetime
    provider_id: str
    security_id: str
    metric: ExpectationMetric
    target_period: str
    target_period_end: date
    value: float
    unit: str
    observed_at: datetime
    source_scope: str
    aggregation_method: str
    sample_count: int
    dispersion: float | None
    raw_provider_payload: object

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.observed_at > self.captured_at:
            raise ValueError("provider observation cannot follow source capture")
        if not self.provider_id.strip() or not self.security_id.strip():
            raise ValueError("provider_id and security_id are required")
        if "kis" in self.provider_id.casefold():
            raise ValueError("KIS expectation evidence is not certified market consensus")
        if not self.target_period.strip() or not self.unit.strip() or not self.source_scope.strip():
            raise ValueError("target period, unit and source scope are required")
        if not math.isfinite(float(self.value)):
            raise ValueError("consensus value must be finite")
        if self.sample_count <= 0:
            raise ValueError("certified consensus requires a positive sample count")
        if not self.aggregation_method.strip():
            raise ValueError("certified consensus requires an aggregation method")
        if self.dispersion is not None and not math.isfinite(float(self.dispersion)):
            raise ValueError("dispersion must be finite when supplied")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": CERTIFIED_CONSENSUS_SOURCE_SCHEMA_VERSION,
            "object_type": "certified_consensus_source",
            "captured_at": self.captured_at.isoformat(),
            "provider_id": self.provider_id,
            "security_id": self.security_id,
            "metric": self.metric.value,
            "target_period": self.target_period,
            "target_period_end": self.target_period_end.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "observed_at": self.observed_at.isoformat(),
            "source_scope": self.source_scope,
            "aggregation_method": self.aggregation_method,
            "sample_count": self.sample_count,
            "dispersion": self.dispersion,
            "raw_provider_payload": self.raw_provider_payload,
            "certification_profile": "independent_market_consensus_export_v1",
            "provider_semantics_certified": True,
            "target_period_semantics_certified": True,
            "metric_semantics_certified": True,
            "aggregation_semantics_certified": True,
            "observation_timestamp_certified": True,
            "market_consensus_certified": True,
            "provider_vintage_certified": False,
            "revision_calculation_certified": False,
            "decision_score_enabled": False,
            "target_price_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.payload_without_id()).encode("utf-8")
        ).hexdigest()

    def observation(self) -> CertifiedExpectationObservation:
        semantics = ExpectationSemantics(
            provider_id=self.provider_id,
            provider_semantics_certified=True,
            target_period_semantics_certified=True,
            metric_semantics_certified=True,
            aggregation_semantics_certified=True,
            observation_timestamp_certified=True,
            provider_vintage_certified=False,
            comparable_prior_snapshot_available=False,
            comparable_snapshot_scope_certified=False,
            revision_calculation_certified=False,
            numeric_evidence_available=True,
            source_scope=self.source_scope,
        )
        return CertifiedExpectationObservation(
            security_id=self.security_id,
            metric=self.metric,
            target_period=self.target_period,
            target_period_end=self.target_period_end,
            expectation_kind=ExpectationKind.MARKET_CONSENSUS,
            value=self.value,
            unit=self.unit,
            observed_at=self.observed_at,
            source_evidence_id=self.snapshot_id,
            semantics=semantics,
            market_consensus_certified=True,
            aggregation_method=self.aggregation_method,
            sample_count=self.sample_count,
            dispersion=self.dispersion,
        )


def _certified_consensus_manifest(
    snapshot: CertifiedConsensusSourceSnapshot,
) -> dict[str, object]:
    return {
        "schema_version": CERTIFIED_CONSENSUS_SOURCE_SCHEMA_VERSION,
        "object_type": "certified_consensus_source",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "provider_id": snapshot.provider_id,
        "security_id": snapshot.security_id,
        "immutable": True,
        "certification_profile": "independent_market_consensus_export_v1",
        "market_consensus_certified": True,
        "decision_score_enabled": False,
        "target_price_enabled": False,
        "automatic_execution_enabled": False,
        "files": ["certified_expectation_source.json"],
    }


def persist_certified_consensus_source(
    snapshot: CertifiedConsensusSourceSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / CERTIFIED_CONSENSUS_SOURCE_REPOSITORY
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    temporary = root / f".{directory.name}.tmp"
    if directory.exists():
        loaded = load_persisted_certified_consensus_source(
            Path(output_root), snapshot.snapshot_id
        )
        if loaded != snapshot:
            raise ValueError("existing certified consensus source conflicts")
        return directory
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "certified_expectation_source.json").write_text(
            json.dumps(snapshot.payload_without_id(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "manifest.json").write_text(
            json.dumps(_certified_consensus_manifest(snapshot), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return directory


def load_persisted_certified_consensus_source(
    artifact_root: str | Path,
    snapshot_id: str,
) -> CertifiedConsensusSourceSnapshot | None:
    root = Path(artifact_root)
    envelope = _load_source_envelope(
        root,
        repository_name=CERTIFIED_CONSENSUS_SOURCE_REPOSITORY,
        snapshot_id=snapshot_id,
        payload_name="certified_expectation_source.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        snapshot = CertifiedConsensusSourceSnapshot(
            captured_at=datetime.fromisoformat(_source_text(payload, "captured_at")),
            provider_id=_source_text(payload, "provider_id"),
            security_id=_source_text(payload, "security_id"),
            metric=ExpectationMetric(_source_text(payload, "metric")),
            target_period=_source_text(payload, "target_period"),
            target_period_end=date.fromisoformat(_source_text(payload, "target_period_end")),
            value=float(payload["value"]),
            unit=_source_text(payload, "unit"),
            observed_at=datetime.fromisoformat(_source_text(payload, "observed_at")),
            source_scope=_source_text(payload, "source_scope"),
            aggregation_method=_source_text(payload, "aggregation_method"),
            sample_count=int(payload["sample_count"]),
            dispersion=(
                None if payload.get("dispersion") is None else float(payload["dispersion"])
            ),
            raw_provider_payload=payload["raw_provider_payload"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_payload = snapshot.payload_without_id()
    expected_manifest = _certified_consensus_manifest(snapshot)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if (
        payload != expected_payload
        or manifest != expected_manifest
        or snapshot.snapshot_id != snapshot_id
        or directory.name != f"{timestamp}__{snapshot.snapshot_id[:12]}"
    ):
        return None
    return snapshot


def certified_expectation_sources_are_canonical(
    artifact_root: str | Path,
    observations: tuple[CertifiedExpectationObservation, ...],
    source_snapshot_ids: tuple[str, ...],
    *,
    captured_at: datetime,
) -> bool:
    """Rebuild every certified consensus row from independent provider evidence."""

    source_ids = set(source_snapshot_ids)
    for observation in observations:
        if not observation.market_consensus_certified:
            continue
        if observation.source_evidence_id not in source_ids:
            return False
        try:
            source = load_persisted_certified_consensus_source(
                artifact_root, observation.source_evidence_id
            )
        except (OSError, ResearchSourceEvidenceError, TypeError, ValueError):
            return False
        if source is None or source.captured_at > captured_at:
            return False
        if source.observation() != observation:
            return False
    return True


__all__ = [
    "CERTIFIED_CONSENSUS_SOURCE_REPOSITORY",
    "CertifiedConsensusSourceSnapshot",
    "ResearchSourceEvidenceError",
    "VALUATION_SOURCE_REPOSITORY",
    "ValuationSourceSnapshot",
    "build_valuation_source_from_evidence",
    "certified_expectation_sources_are_canonical",
    "load_persisted_certified_consensus_source",
    "load_persisted_valuation_source",
    "persist_certified_consensus_source",
    "persist_valuation_source",
    "rebuild_valuation_evidence_from_source",
    "validate_valuation_source_upstream",
]
