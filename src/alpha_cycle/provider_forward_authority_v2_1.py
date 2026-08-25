"""Provider-specific replay authority for forward-estimate source captures.

The first supported parser is deliberately narrow.  It proves that a persisted source was
captured from the KIS ``estimate-perform`` endpoint and reproduces its opaque provider cells.
KIS does not document enough semantics to promote those cells to typed financial estimates,
historical revisions, issuer guidance, or market consensus.  Those capabilities therefore
remain fail closed even when a caller supplies optimistic normalized flags.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.expectations import ExpectationIntelligenceSnapshot
from alpha_cycle.providers.kis_research import (
    KIS_ESTIMATE_PERFORM_ENDPOINT,
    KIS_ESTIMATE_PERFORM_TR_ID,
    KIS_RESEARCH_SOURCE_SCOPE,
    KisEstimatePerformEvidence,
)

SCHEMA_VERSION = 1
PARSER_ID = "alpha_cycle.kis_estimate_perform.opaque_cells"
PARSER_VERSION = "1.0.0"
PROVIDER_ID = "korea_investment_openapi"
REPOSITORY_NAME = "provider_forward_authority_v2_1"
KOREA_TZ = ZoneInfo("Asia/Seoul")
_SOURCE_FILES = ("manifest.json", "records.json", "raw_estimate_perform.json")
_OUTPUT_FILES = (
    "authority.json",
    "source_manifest.json",
    "source_records.json",
    "raw_estimate_perform.json",
)


class ProviderForwardAuthorityError(ValueError):
    """Raised when a provider capture or its independent replay is not trustworthy."""


class SourceSemanticClass(StrEnum):
    OFFICIAL_ISSUER_ACTUAL = "official_issuer_actual"
    OFFICIAL_ISSUER_GUIDANCE = "official_issuer_guidance"
    SINGLE_BROKER_ESTIMATE = "single_broker_estimate"
    MULTIPLE_PROVIDER_CONSENSUS = "multiple_provider_consensus"
    DERIVED_MODEL_ESTIMATE = "derived_model_estimate"
    UNSUPPORTED_UNKNOWN = "unsupported_unknown"


@dataclass(frozen=True)
class OpaqueProviderCell:
    """One exact provider cell whose financial meaning is intentionally unresolved."""

    security_id: str
    output_name: str
    row_number_1_based: int
    field_name: str
    raw_value: str
    period_label_candidate: str | None

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "output_name": self.output_name,
            "row_number_1_based": self.row_number_1_based,
            "field_name": self.field_name,
            "raw_value": self.raw_value,
            "period_label_candidate": self.period_label_candidate,
            "normalized_metric": None,
            "normalized_value": None,
            "unit": None,
            "currency": None,
            "estimate_type": "provider_defined_opaque_cell",
            "semantic_class": SourceSemanticClass.UNSUPPORTED_UNKNOWN.value,
            "numeric_forward_authority": False,
        }


@dataclass(frozen=True)
class ProviderForwardAuthorityArtifact:
    """Content-addressed result of replaying an exact provider source capture."""

    source_snapshot_id: str
    source_captured_at: datetime
    evaluation_date: date
    research_cutoff_at: datetime
    raw_archive_sha256: str
    source_records_sha256: str
    source_manifest_sha256: str
    symbols: tuple[str, ...]
    retrieved_at_by_symbol: tuple[tuple[str, datetime], ...]
    original_response_sha256_by_symbol: tuple[tuple[str, str], ...]
    cells: tuple[OpaqueProviderCell, ...]

    def __post_init__(self) -> None:
        _sha(self.source_snapshot_id, "source_snapshot_id")
        _sha(self.raw_archive_sha256, "raw_archive_sha256")
        _sha(self.source_records_sha256, "source_records_sha256")
        _sha(self.source_manifest_sha256, "source_manifest_sha256")
        if self.source_captured_at.tzinfo is None:
            raise ProviderForwardAuthorityError("source_captured_at must be timezone-aware")
        if self.research_cutoff_at.tzinfo is None:
            raise ProviderForwardAuthorityError("research_cutoff_at must be timezone-aware")
        if self.research_cutoff_at.astimezone(KOREA_TZ).date() != self.evaluation_date:
            raise ProviderForwardAuthorityError("research cutoff/evaluation date mismatch")
        if self.source_captured_at > self.research_cutoff_at:
            raise ProviderForwardAuthorityError("provider source captured after research cutoff")
        if self.symbols != tuple(sorted(set(self.symbols))):
            raise ProviderForwardAuthorityError("symbols must be unique and sorted")
        if tuple(item[0] for item in self.retrieved_at_by_symbol) != self.symbols:
            raise ProviderForwardAuthorityError("retrieval metadata does not match symbols")
        retrieval_times = tuple(item[1] for item in self.retrieved_at_by_symbol)
        if any(value.tzinfo is None for value in retrieval_times):
            raise ProviderForwardAuthorityError("retrieved_at must be timezone-aware")
        if any(value > self.research_cutoff_at for value in retrieval_times):
            raise ProviderForwardAuthorityError("provider record retrieved after research cutoff")
        if not retrieval_times or max(retrieval_times) != self.source_captured_at:
            raise ProviderForwardAuthorityError(
                "source_captured_at must equal the latest record retrieval"
            )
        if tuple(item[0] for item in self.original_response_sha256_by_symbol) != self.symbols:
            raise ProviderForwardAuthorityError("response hashes do not match symbols")
        for _, value in self.original_response_sha256_by_symbol:
            _sha(value, "original_response_sha256")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "provider_id": PROVIDER_ID,
            "endpoint": KIS_ESTIMATE_PERFORM_ENDPOINT,
            "tr_id": KIS_ESTIMATE_PERFORM_TR_ID,
            "source_scope": KIS_RESEARCH_SOURCE_SCOPE,
            "parser_id": PARSER_ID,
            "parser_version": PARSER_VERSION,
            "source_snapshot_id": self.source_snapshot_id,
            "source_captured_at": self.source_captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "source_publication_time": None,
            "source_publication_time_recoverable": False,
            "captured_at": self.source_captured_at.isoformat(),
            "raw_archive_sha256": self.raw_archive_sha256,
            "source_records_sha256": self.source_records_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "original_http_response_bytes_archived": False,
            "original_response_sha256_by_symbol": [
                {"security_id": symbol, "sha256": digest}
                for symbol, digest in self.original_response_sha256_by_symbol
            ],
            "symbols": list(self.symbols),
            "retrieved_at_by_symbol": [
                {"security_id": symbol, "retrieved_at": value.isoformat()}
                for symbol, value in self.retrieved_at_by_symbol
            ],
            "revision_identity": self.source_snapshot_id,
            "revision_sequence": 0,
            "revision_history_complete": False,
            "historical_point_in_time_complete": False,
            "provider_capture_replay_integrity": True,
            "provider_source_authority": False,
            "provider_forward_numeric_authority": False,
            "issuer_guidance_authority": False,
            "single_broker_authority": False,
            "market_consensus_authority": False,
            "revision_authority": False,
            "semantic_class": SourceSemanticClass.UNSUPPORTED_UNKNOWN.value,
            "authority_blockers": [
                "trusted_provider_capture_attestation_unavailable",
                "provider_financial_metric_semantics_unavailable",
                "forecast_column_period_alignment_not_certified",
                "forecast_scale_continuity_not_certified",
                "aggregation_semantics_unavailable",
                "provider_vintage_history_unavailable",
            ],
            "cells": [item.payload() for item in self.cells],
            "decision_score_enabled": False,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def artifact_id(self) -> str:
        return _digest(_canonical_bytes(self.payload_without_id()))

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "artifact_id": self.artifact_id}


def build_kis_provider_authority(
    source_directory: str | Path,
    *,
    evaluation_date: date,
    research_cutoff_at: datetime,
) -> ProviderForwardAuthorityArtifact:
    """Replay one persisted KIS capture without making a network call."""

    directory = _plain_directory(Path(source_directory), label="KIS source snapshot")
    source_bytes = {
        name: _read_plain_file(directory / name, directory=directory)
        for name in _SOURCE_FILES
    }
    manifest = _json_object(source_bytes["manifest.json"], label="source manifest")
    records_payload = _json_array(source_bytes["records.json"], label="source records")
    raw_payload = _json_object(
        source_bytes["raw_estimate_perform.json"], label="raw estimate-perform"
    )
    snapshot = _reconstruct_snapshot(manifest, records_payload, raw_payload)
    if research_cutoff_at.tzinfo is None or research_cutoff_at.utcoffset() is None:
        raise ProviderForwardAuthorityError("research_cutoff_at must be timezone-aware")
    if snapshot.captured_at > research_cutoff_at:
        raise ProviderForwardAuthorityError("provider source captured after research cutoff")
    cells = _opaque_cells(raw_payload, snapshot.symbols)
    return ProviderForwardAuthorityArtifact(
        source_snapshot_id=snapshot.snapshot_id,
        source_captured_at=snapshot.captured_at,
        evaluation_date=evaluation_date,
        research_cutoff_at=research_cutoff_at,
        raw_archive_sha256=_digest(source_bytes["raw_estimate_perform.json"]),
        source_records_sha256=_digest(source_bytes["records.json"]),
        source_manifest_sha256=_digest(source_bytes["manifest.json"]),
        symbols=snapshot.symbols,
        retrieved_at_by_symbol=tuple(
            (item.symbol, item.retrieved_at) for item in snapshot.records
        ),
        original_response_sha256_by_symbol=tuple(
            (item.symbol, item.raw_response_sha256) for item in snapshot.records
        ),
        cells=cells,
    )


def publish_kis_provider_authority(
    source_directory: str | Path,
    *,
    evaluation_date: date,
    research_cutoff_at: datetime,
    output_root: str | Path,
) -> Path:
    """Publish exact source bytes plus their deterministic provider replay result."""

    source = _plain_directory(Path(source_directory), label="KIS source snapshot")
    artifact = build_kis_provider_authority(
        source,
        evaluation_date=evaluation_date,
        research_cutoff_at=research_cutoff_at,
    )
    root = Path(output_root)
    if root.exists() or root.is_symlink():
        root = _plain_directory(root, label="provider authority repository")
    else:
        root.mkdir(parents=True)
        root = _plain_directory(root, label="provider authority repository")
    name = (
        artifact.source_captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + f"__{artifact.artifact_id[:12]}"
    )
    destination = root / name
    if destination.exists() or destination.is_symlink():
        loaded = replay_kis_provider_authority(
            destination,
            evaluation_date=evaluation_date,
            research_cutoff_at=research_cutoff_at,
        )
        if loaded.artifact_id != artifact.artifact_id:
            raise ProviderForwardAuthorityError("immutable artifact identity collision")
        return destination
    temporary = root / f".{name}.{os.getpid()}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ProviderForwardAuthorityError("provider authority temporary path already exists")
    temporary.mkdir()
    try:
        (temporary / "authority.json").write_bytes(_pretty_bytes(artifact.payload()))
        shutil.copyfile(source / "manifest.json", temporary / "source_manifest.json")
        shutil.copyfile(source / "records.json", temporary / "source_records.json")
        shutil.copyfile(
            source / "raw_estimate_perform.json",
            temporary / "raw_estimate_perform.json",
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "object_type": REPOSITORY_NAME,
            "artifact_id": artifact.artifact_id,
            "captured_at": artifact.source_captured_at.isoformat(),
            "immutable": True,
            "files": list(_OUTPUT_FILES),
            "file_sha256": {
                name: _digest(_read_plain_file(temporary / name, directory=temporary))
                for name in _OUTPUT_FILES
            },
        }
        (temporary / "manifest.json").write_bytes(_pretty_bytes(manifest))
        staged = replay_kis_provider_authority(
            temporary,
            evaluation_date=evaluation_date,
            research_cutoff_at=research_cutoff_at,
            expected_artifact_id=artifact.artifact_id,
            _staged=True,
        )
        if staged.artifact_id != artifact.artifact_id:
            raise ProviderForwardAuthorityError("staged provider replay identity mismatch")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    replayed = replay_kis_provider_authority(
        destination,
        evaluation_date=evaluation_date,
        research_cutoff_at=research_cutoff_at,
    )
    if replayed.artifact_id != artifact.artifact_id:
        raise ProviderForwardAuthorityError("published provider replay identity mismatch")
    return destination


def replay_kis_provider_authority(
    artifact_directory: str | Path,
    *,
    evaluation_date: date,
    research_cutoff_at: datetime,
    expected_artifact_id: str | None = None,
    _staged: bool = False,
) -> ProviderForwardAuthorityArtifact:
    """Independently rerun the KIS parser from persisted raw bytes only."""

    directory = _plain_directory(Path(artifact_directory), label="provider authority artifact")
    manifest_bytes = _read_plain_file(directory / "manifest.json", directory=directory)
    manifest = _json_object(manifest_bytes, label="authority manifest")
    if set(manifest) != {
        "schema_version", "object_type", "artifact_id", "captured_at", "immutable",
        "files", "file_sha256",
    }:
        raise ProviderForwardAuthorityError("authority manifest fields are not canonical")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("immutable") is not True:
        raise ProviderForwardAuthorityError("authority manifest contract mismatch")
    if manifest.get("object_type") != REPOSITORY_NAME:
        raise ProviderForwardAuthorityError("authority manifest object_type mismatch")
    if manifest.get("files") != list(_OUTPUT_FILES):
        raise ProviderForwardAuthorityError("authority manifest file set mismatch")
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(_OUTPUT_FILES):
        raise ProviderForwardAuthorityError("authority manifest hashes are incomplete")
    persisted = {
        name: _read_plain_file(directory / name, directory=directory)
        for name in _OUTPUT_FILES
    }
    for name, value in persisted.items():
        if hashes.get(name) != _digest(value):
            raise ProviderForwardAuthorityError(f"persisted source mutation: {name}")
    source_manifest = _json_object(persisted["source_manifest.json"], label="source manifest")
    source_records = _json_array(persisted["source_records.json"], label="source records")
    raw = _json_object(persisted["raw_estimate_perform.json"], label="raw source")
    snapshot = _reconstruct_snapshot(source_manifest, source_records, raw)
    replayed = ProviderForwardAuthorityArtifact(
        source_snapshot_id=snapshot.snapshot_id,
        source_captured_at=snapshot.captured_at,
        evaluation_date=evaluation_date,
        research_cutoff_at=research_cutoff_at,
        raw_archive_sha256=_digest(persisted["raw_estimate_perform.json"]),
        source_records_sha256=_digest(persisted["source_records.json"]),
        source_manifest_sha256=_digest(persisted["source_manifest.json"]),
        symbols=snapshot.symbols,
        retrieved_at_by_symbol=tuple((item.symbol, item.retrieved_at) for item in snapshot.records),
        original_response_sha256_by_symbol=tuple(
            (item.symbol, item.raw_response_sha256) for item in snapshot.records
        ),
        cells=_opaque_cells(raw, snapshot.symbols),
    )
    declared = _required_sha(manifest.get("artifact_id"), "manifest artifact_id")
    stored = _json_object(persisted["authority.json"], label="normalized authority")
    if stored != replayed.payload():
        raise ProviderForwardAuthorityError(
            "normalized artifact mutation or parser replay mismatch"
        )
    if replayed.artifact_id != declared:
        raise ProviderForwardAuthorityError("normalized artifact identity mismatch")
    manifest_captured_at = _aware_datetime(manifest.get("captured_at"), "captured_at")
    if (
        manifest_captured_at != replayed.source_captured_at
        or manifest.get("captured_at") != replayed.source_captured_at.isoformat()
    ):
        raise ProviderForwardAuthorityError("authority manifest capture timestamp mismatch")
    expected_directory = (
        replayed.source_captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + f"__{replayed.artifact_id[:12]}"
    )
    if not _staged and directory.name != expected_directory:
        raise ProviderForwardAuthorityError("authority directory identity mismatch")
    if expected_artifact_id is not None and replayed.artifact_id != _required_sha(
        expected_artifact_id, "expected_artifact_id"
    ):
        raise ProviderForwardAuthorityError("stale or substituted provider revision")
    return replayed


def replay_persisted_kis_provider_authority(
    artifact_directory: str | Path,
    *,
    evaluation_date: date,
    maximum_research_cutoff_at: datetime,
    expected_artifact_id: str,
) -> ProviderForwardAuthorityArtifact:
    """Replay an artifact's bound cutoff while enforcing the caller's latest PIT time."""

    if maximum_research_cutoff_at.tzinfo is None:
        raise ProviderForwardAuthorityError(
            "maximum_research_cutoff_at must be timezone-aware"
        )
    directory = _plain_directory(Path(artifact_directory), label="provider authority artifact")
    authority = _json_object(
        _read_plain_file(directory / "authority.json", directory=directory),
        label="normalized authority",
    )
    cutoff = _aware_datetime(authority.get("research_cutoff_at"), "research_cutoff_at")
    if cutoff > maximum_research_cutoff_at:
        raise ProviderForwardAuthorityError("provider artifact cutoff exceeds package cutoff")
    return replay_kis_provider_authority(
        directory,
        evaluation_date=evaluation_date,
        research_cutoff_at=cutoff,
        expected_artifact_id=expected_artifact_id,
    )


def provider_authority_can_certify_expectation(
    artifact: ProviderForwardAuthorityArtifact,
    *,
    provider_id: str,
    security_id: str,
    metric: str,
    target_period: str,
    market_consensus_certified: bool,
) -> bool:
    """Fail-closed package boundary; caller labels never create provider authority."""

    _ = artifact, security_id, metric, target_period, market_consensus_certified
    if provider_id != PROVIDER_ID:
        return False
    # The current KIS parser proves only opaque cells.  None is a typed expectation.
    return False


def _reconstruct_snapshot(
    manifest: dict[str, object], records_payload: list[object], raw: dict[str, object]
) -> ExpectationIntelligenceSnapshot:
    expected_manifest_keys = {
        "schema_version", "snapshot_id", "captured_at", "provider", "source_scope",
        "symbols", "semantic_status", "consensus_certified", "revision_certified",
        "account_api_enabled", "holdings_api_enabled", "balance_api_enabled",
        "order_api_enabled", "files",
    }
    if set(manifest) != expected_manifest_keys:
        raise ProviderForwardAuthorityError("KIS source manifest fields are not canonical")
    if manifest.get("schema_version") != 1 or manifest.get("provider") != PROVIDER_ID:
        raise ProviderForwardAuthorityError("KIS source manifest provider/schema mismatch")
    if manifest.get("source_scope") != KIS_RESEARCH_SOURCE_SCOPE:
        raise ProviderForwardAuthorityError("KIS source manifest scope mismatch")
    if manifest.get("semantic_status") != "raw_structure_only":
        raise ProviderForwardAuthorityError("KIS source must remain raw_structure_only")
    for field in (
        "consensus_certified", "revision_certified", "account_api_enabled",
        "holdings_api_enabled", "balance_api_enabled", "order_api_enabled",
    ):
        if manifest.get(field) is not False:
            raise ProviderForwardAuthorityError(f"KIS source must keep {field}=false")
    if manifest.get("files") != ["structure.csv", "records.json", "raw_estimate_perform.json"]:
        raise ProviderForwardAuthorityError("KIS source manifest file set mismatch")
    records: list[KisEstimatePerformEvidence] = []
    for index, value in enumerate(records_payload):
        if not isinstance(value, dict):
            raise ProviderForwardAuthorityError(f"source record {index} is not an object")
        record = cast(dict[str, object], value)
        if set(record) != {
            "symbol", "retrieved_at", "provider", "endpoint", "tr_id", "source_scope",
            "raw_response_sha256", "raw_payload",
        }:
            raise ProviderForwardAuthorityError("source record fields are not canonical")
        if record.get("provider") != PROVIDER_ID:
            raise ProviderForwardAuthorityError("provider name spoofing detected")
        if record.get("endpoint") != KIS_ESTIMATE_PERFORM_ENDPOINT:
            raise ProviderForwardAuthorityError("provider endpoint mismatch")
        if record.get("tr_id") != KIS_ESTIMATE_PERFORM_TR_ID:
            raise ProviderForwardAuthorityError("provider transaction id mismatch")
        payload = record.get("raw_payload")
        if not isinstance(payload, dict):
            raise ProviderForwardAuthorityError("source raw_payload is not an object")
        if payload.get("rt_cd") != "0":
            raise ProviderForwardAuthorityError("KIS source response is not successful")
        output1 = payload.get("output1")
        if not isinstance(output1, dict):
            raise ProviderForwardAuthorityError("KIS source output1 is not an object")
        reported_security = str(output1.get("sht_cd", "")).strip()
        if reported_security.startswith("A"):
            reported_security = reported_security[1:]
        if reported_security != str(record.get("symbol", "")):
            raise ProviderForwardAuthorityError("provider-reported security mismatch")
        item = KisEstimatePerformEvidence(
            symbol=str(record.get("symbol", "")),
            retrieved_at=_aware_datetime(record.get("retrieved_at"), "retrieved_at"),
            endpoint=str(record["endpoint"]),
            tr_id=str(record["tr_id"]),
            source_scope=str(record.get("source_scope", "")),
            raw_response_sha256=_required_sha(
                record.get("raw_response_sha256"), "raw_response_sha256"
            ),
            raw_payload=cast(dict[str, object], payload),
        )
        if raw.get(item.symbol) != dict(item.raw_payload):
            raise ProviderForwardAuthorityError("records/raw archive payload mismatch")
        records.append(item)
    captured = _aware_datetime(manifest.get("captured_at"), "captured_at")
    snapshot = ExpectationIntelligenceSnapshot(
        captured_at=captured,
        provider=PROVIDER_ID,
        source_scope=KIS_RESEARCH_SOURCE_SCOPE,
        records=tuple(records),
    )
    if manifest.get("symbols") != list(snapshot.symbols) or set(raw) != set(snapshot.symbols):
        raise ProviderForwardAuthorityError("KIS source security identity mismatch")
    if snapshot.snapshot_id != _required_sha(manifest.get("snapshot_id"), "snapshot_id"):
        raise ProviderForwardAuthorityError("KIS source snapshot identity mismatch")
    return snapshot


def _opaque_cells(
    raw: dict[str, object], symbols: tuple[str, ...]
) -> tuple[OpaqueProviderCell, ...]:
    result: list[OpaqueProviderCell] = []
    for symbol in symbols:
        payload = raw.get(symbol)
        if not isinstance(payload, dict):
            raise ProviderForwardAuthorityError(f"raw source missing security {symbol}")
        periods_raw = payload.get("output4")
        if not isinstance(periods_raw, list):
            raise ProviderForwardAuthorityError(f"{symbol}.output4 must be an array")
        periods: list[str] = []
        for row in periods_raw:
            if not isinstance(row, dict) or set(row) != {"dt"}:
                raise ProviderForwardAuthorityError(f"{symbol}.output4 schema mismatch")
            period = str(row["dt"]).strip()
            if not period:
                raise ProviderForwardAuthorityError("empty KIS period label")
            periods.append(period)
        for output_name in ("output2", "output3"):
            rows = payload.get(output_name)
            if not isinstance(rows, list):
                raise ProviderForwardAuthorityError(f"{symbol}.{output_name} must be an array")
            for row_index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    raise ProviderForwardAuthorityError("KIS output row must be an object")
                expected = {f"data{index}" for index in range(1, len(periods) + 1)}
                if set(row) != expected:
                    raise ProviderForwardAuthorityError("KIS opaque DATA field set mismatch")
                for field_index, field in enumerate(sorted(expected, key=lambda x: int(x[4:]))):
                    value = row[field]
                    if value is None:
                        raise ProviderForwardAuthorityError(
                            "unsupported KIS field cannot become zero"
                        )
                    result.append(
                        OpaqueProviderCell(
                            security_id=symbol,
                            output_name=output_name,
                            row_number_1_based=row_index,
                            field_name=field,
                            raw_value=str(value),
                            # Candidate only: KIS does not certify the positional relationship.
                            period_label_candidate=periods[field_index],
                        )
                    )
    return tuple(result)


def _plain_directory(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ProviderForwardAuthorityError(f"{label} must be a regular directory")
    _reject_reparse(path, label)
    lexical = Path(os.path.abspath(path))
    for component in reversed((lexical, *lexical.parents)):
        if not component.exists():
            continue
        if component.is_symlink():
            raise ProviderForwardAuthorityError(f"{label} traverses a symlink")
        _reject_reparse(component, label)
    resolved = lexical.resolve(strict=True)
    return resolved


def _read_plain_file(path: Path, *, directory: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ProviderForwardAuthorityError(f"provider artifact file is missing: {path.name}")
    _reject_reparse(path, path.name)
    resolved = path.resolve(strict=True)
    if resolved.parent != directory.resolve(strict=True):
        raise ProviderForwardAuthorityError("provider artifact file escapes its directory")
    return resolved.read_bytes()


def _reject_reparse(path: Path, label: str) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        raise ProviderForwardAuthorityError(f"{label} cannot be a symlink")
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if attributes & reparse:
        raise ProviderForwardAuthorityError(f"{label} cannot be a Windows reparse point")


def _json_object(value: bytes, *, label: str) -> dict[str, object]:
    parsed = _json(value, label=label)
    if not isinstance(parsed, dict):
        raise ProviderForwardAuthorityError(f"{label} must be a JSON object")
    return {str(key): item for key, item in parsed.items()}


def _json_array(value: bytes, *, label: str) -> list[object]:
    parsed = _json(value, label=label)
    if not isinstance(parsed, list):
        raise ProviderForwardAuthorityError(f"{label} must be a JSON array")
    return cast(list[object], parsed)


def _json(value: bytes, *, label: str) -> Any:
    try:
        return json.loads(value.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderForwardAuthorityError(f"{label} is not canonical UTF-8 JSON") from exc


def _aware_datetime(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ProviderForwardAuthorityError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProviderForwardAuthorityError(f"{field} must be timezone-aware")
    return parsed


def _required_sha(value: object, field: str) -> str:
    return _sha(str(value), field)


def _sha(value: str, field: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ProviderForwardAuthorityError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _pretty_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "ProviderForwardAuthorityArtifact",
    "ProviderForwardAuthorityError",
    "SourceSemanticClass",
    "build_kis_provider_authority",
    "provider_authority_can_certify_expectation",
    "publish_kis_provider_authority",
    "replay_persisted_kis_provider_authority",
    "replay_kis_provider_authority",
]
