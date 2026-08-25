"""Frozen source selection for Decision System v2.1 live typed research.

The manifest in this module is provenance only. It binds an exact set of already-persisted
source snapshot bytes for deterministic replay; it does not certify provider semantics,
valuation authority, market consensus, or research-package readiness.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

SOURCE_MANIFEST_SCHEMA_VERSION = 1
_SOURCE_MANIFEST_DIRECTORY = "live_typed_source_manifest_v2_1"


class LiveTypedSourceManifestError(ValueError):
    """Raised when a frozen live-source selection cannot be trusted or replayed."""


@dataclass(frozen=True)
class SourceFileBinding:
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_safe_relative_path(self.relative_path, "relative_path")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")
        _validate_sha(self.sha256, "sha256")

    def payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class FrozenSourceSnapshot:
    role: str
    snapshot_id: str
    captured_at: datetime
    evaluation_date: date | None
    snapshot_path: str
    files: tuple[SourceFileBinding, ...]

    def __post_init__(self) -> None:
        _require_text(self.role, "role")
        _validate_sha(self.snapshot_id, "snapshot_id")
        _require_aware(self.captured_at, "captured_at")
        _require_safe_relative_path(self.snapshot_path, "snapshot_path")
        if not self.files:
            raise ValueError("frozen source snapshot requires at least one bound file")
        paths = tuple(item.relative_path for item in self.files)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("source files must be unique and sorted by relative_path")
        if "manifest.json" not in paths:
            raise ValueError("source files must bind manifest.json")

    def payload(self) -> dict[str, object]:
        return {
            "role": self.role,
            "snapshot_id": self.snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": (
                self.evaluation_date.isoformat() if self.evaluation_date is not None else None
            ),
            "snapshot_path": self.snapshot_path,
            "files": [item.payload() for item in self.files],
        }


@dataclass(frozen=True)
class LiveTypedSourceManifest:
    evaluation_date: date
    research_cutoff_at: datetime
    frozen_at: datetime
    sources: tuple[FrozenSourceSnapshot, ...]

    def __post_init__(self) -> None:
        _require_aware(self.research_cutoff_at, "research_cutoff_at")
        _require_aware(self.frozen_at, "frozen_at")
        if not self.sources:
            raise ValueError("live typed source manifest requires at least one source")
        roles = tuple(item.role for item in self.sources)
        if roles != tuple(sorted(roles)) or len(set(roles)) != len(roles):
            raise ValueError("source roles must be unique and sorted")
        if self.frozen_at > self.research_cutoff_at:
            raise ValueError("frozen_at cannot follow research_cutoff_at")
        for source in self.sources:
            if source.captured_at > self.frozen_at:
                raise ValueError("source captured_at cannot follow frozen_at")
            if (
                source.evaluation_date is not None
                and source.evaluation_date != self.evaluation_date
            ):
                raise ValueError("source evaluation_date differs from manifest evaluation_date")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "frozen_at": self.frozen_at.isoformat(),
            "sources": [item.payload() for item in self.sources],
            "provenance_only": True,
            "provider_authority_certified": False,
            "valuation_authority_certified": False,
            "market_consensus_authority_certified": False,
        }

    @property
    def manifest_id(self) -> str:
        return _sha(self.payload_without_id())


def freeze_live_typed_source_manifest(
    *,
    artifact_root: str | Path,
    source_directories: dict[str, str | Path],
    evaluation_date: date,
    research_cutoff_at: datetime,
    frozen_at: datetime,
) -> LiveTypedSourceManifest:
    """Bind exact bytes for an already-persisted set of live/repository source snapshots."""

    _require_aware(research_cutoff_at, "research_cutoff_at")
    _require_aware(frozen_at, "frozen_at")
    root = _trusted_root(Path(artifact_root))
    if not source_directories:
        raise LiveTypedSourceManifestError("source_directories cannot be empty")

    sources: list[FrozenSourceSnapshot] = []
    for role, raw_directory in sorted(source_directories.items()):
        _require_text(role, "source role")
        directory = _trusted_snapshot_directory(root, Path(raw_directory))
        manifest_path = directory / "manifest.json"
        source_manifest = _load_json_object(manifest_path)
        snapshot_id = _required_text(source_manifest, "snapshot_id")
        _validate_sha(snapshot_id, "source snapshot_id")
        captured_at = _parse_aware_datetime(
            _required_text(source_manifest, "captured_at"),
            "source captured_at",
        )
        if captured_at > frozen_at:
            raise LiveTypedSourceManifestError(
                f"source {role} was captured after frozen_at"
            )
        source_evaluation_date = _optional_date(source_manifest.get("evaluation_date"))
        if source_evaluation_date is not None and source_evaluation_date != evaluation_date:
            raise LiveTypedSourceManifestError(
                f"source {role} evaluation_date differs from requested evaluation_date"
            )
        declared_files = _declared_files(source_manifest)
        bound_names = tuple(sorted({"manifest.json", *declared_files}))
        bindings = tuple(_bind_file(directory, name) for name in bound_names)
        sources.append(
            FrozenSourceSnapshot(
                role=role,
                snapshot_id=snapshot_id,
                captured_at=captured_at,
                evaluation_date=source_evaluation_date,
                snapshot_path=directory.relative_to(root).as_posix(),
                files=bindings,
            )
        )

    return LiveTypedSourceManifest(
        evaluation_date=evaluation_date,
        research_cutoff_at=research_cutoff_at,
        frozen_at=frozen_at,
        sources=tuple(sources),
    )


def persist_live_typed_source_manifest(
    manifest: LiveTypedSourceManifest,
    *,
    artifact_root: str | Path,
) -> Path:
    """Publish a content-addressed source manifest without a mutable latest pointer."""

    root = _trusted_root(Path(artifact_root))
    repository = root / _SOURCE_MANIFEST_DIRECTORY
    if repository.is_symlink():
        raise LiveTypedSourceManifestError("source-manifest repository cannot be a symlink")
    repository.mkdir(parents=True, exist_ok=True)
    path = repository / f"{manifest.manifest_id}.json"
    payload = dict(manifest.payload_without_id())
    payload["manifest_id"] = manifest.manifest_id
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if path.exists():
        loaded = load_live_typed_source_manifest(path)
        if loaded != manifest:
            raise LiveTypedSourceManifestError(
                "existing source manifest conflicts with requested content identity"
            )
        return path

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{manifest.manifest_id}.",
        suffix=".tmp",
        dir=repository,
    )
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_live_typed_source_manifest(path: str | Path) -> LiveTypedSourceManifest:
    source = Path(path)
    payload = _load_json_object(source)
    _require_exact_fields(
        payload,
        {
            "schema_version",
            "manifest_id",
            "evaluation_date",
            "research_cutoff_at",
            "frozen_at",
            "sources",
            "provenance_only",
            "provider_authority_certified",
            "valuation_authority_certified",
            "market_consensus_authority_certified",
        },
        "live typed source manifest",
    )
    if _required_int(payload, "schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise LiveTypedSourceManifestError("unsupported live typed source manifest schema")
    if payload.get("provenance_only") is not True:
        raise LiveTypedSourceManifestError("source manifest must remain provenance-only")
    for field in (
        "provider_authority_certified",
        "valuation_authority_certified",
        "market_consensus_authority_certified",
    ):
        if payload.get(field) is not False:
            raise LiveTypedSourceManifestError(f"source manifest cannot certify {field}")

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise LiveTypedSourceManifestError("sources must be a JSON array")
    sources = tuple(_parse_source(_object(item, "source")) for item in raw_sources)
    manifest = LiveTypedSourceManifest(
        evaluation_date=_parse_date(_required_text(payload, "evaluation_date"), "evaluation_date"),
        research_cutoff_at=_parse_aware_datetime(
            _required_text(payload, "research_cutoff_at"),
            "research_cutoff_at",
        ),
        frozen_at=_parse_aware_datetime(_required_text(payload, "frozen_at"), "frozen_at"),
        sources=sources,
    )
    declared = _required_text(payload, "manifest_id")
    _validate_sha(declared, "manifest_id")
    if manifest.manifest_id != declared or source.stem != declared:
        raise LiveTypedSourceManifestError("source manifest content identity mismatch")
    return manifest


def verify_live_typed_source_manifest(
    manifest: LiveTypedSourceManifest,
    *,
    artifact_root: str | Path,
) -> None:
    """Replay-check every selected source path, source manifest, and bound file byte-for-byte."""

    root = _trusted_root(Path(artifact_root))
    for source in manifest.sources:
        directory = _trusted_snapshot_directory(root, root / source.snapshot_path)
        persisted_manifest = _load_json_object(directory / "manifest.json")
        if _required_text(persisted_manifest, "snapshot_id") != source.snapshot_id:
            raise LiveTypedSourceManifestError(
                f"source snapshot identity changed during replay: {source.role}"
            )
        captured_at = _parse_aware_datetime(
            _required_text(persisted_manifest, "captured_at"),
            "source captured_at",
        )
        if captured_at != source.captured_at:
            raise LiveTypedSourceManifestError(
                f"source captured_at changed during replay: {source.role}"
            )
        evaluation_date = _optional_date(persisted_manifest.get("evaluation_date"))
        if evaluation_date != source.evaluation_date:
            raise LiveTypedSourceManifestError(
                f"source evaluation_date changed during replay: {source.role}"
            )
        expected_names = tuple(item.relative_path for item in source.files)
        actual_names = tuple(sorted({"manifest.json", *_declared_files(persisted_manifest)}))
        if actual_names != expected_names:
            raise LiveTypedSourceManifestError(
                f"source declared file set changed during replay: {source.role}"
            )
        for binding in source.files:
            if _bind_file(directory, binding.relative_path) != binding:
                changed_file = f"{source.role}/{binding.relative_path}"
                raise LiveTypedSourceManifestError(
                    f"source file bytes changed during replay: {changed_file}"
                )


def _parse_source(payload: dict[str, Any]) -> FrozenSourceSnapshot:
    _require_exact_fields(
        payload,
        {"role", "snapshot_id", "captured_at", "evaluation_date", "snapshot_path", "files"},
        "source",
    )
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise LiveTypedSourceManifestError("source files must be a JSON array")
    evaluation_raw = payload.get("evaluation_date")
    evaluation_date = None if evaluation_raw is None else _parse_date(
        _text(evaluation_raw, "evaluation_date"),
        "evaluation_date",
    )
    return FrozenSourceSnapshot(
        role=_required_text(payload, "role"),
        snapshot_id=_required_text(payload, "snapshot_id"),
        captured_at=_parse_aware_datetime(
            _required_text(payload, "captured_at"),
            "captured_at",
        ),
        evaluation_date=evaluation_date,
        snapshot_path=_required_text(payload, "snapshot_path"),
        files=tuple(_parse_file(_object(item, "source file")) for item in raw_files),
    )


def _parse_file(payload: dict[str, Any]) -> SourceFileBinding:
    _require_exact_fields(payload, {"relative_path", "size_bytes", "sha256"}, "source file")
    return SourceFileBinding(
        relative_path=_required_text(payload, "relative_path"),
        size_bytes=_required_int(payload, "size_bytes"),
        sha256=_required_text(payload, "sha256"),
    )


def _trusted_root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise LiveTypedSourceManifestError(f"artifact_root must be a real directory: {path}")
    return path.resolve()


def _trusted_snapshot_directory(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink() or not candidate.is_dir():
        raise LiveTypedSourceManifestError(f"source snapshot must be a real directory: {candidate}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise LiveTypedSourceManifestError("source snapshot escapes artifact_root")
    manifest = resolved / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise LiveTypedSourceManifestError("source snapshot requires a regular manifest.json")
    return resolved


def _declared_files(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("files")
    if not isinstance(raw, list):
        raise LiveTypedSourceManifestError("source manifest files must be a JSON array")
    files = tuple(_text(item, "source file") for item in raw)
    if len(set(files)) != len(files):
        raise LiveTypedSourceManifestError("source manifest files cannot contain duplicates")
    for item in files:
        _require_safe_relative_path(item, "source file")
    return tuple(sorted(files))


def _bind_file(directory: Path, relative_path: str) -> SourceFileBinding:
    _require_safe_relative_path(relative_path, "source file")
    path = directory / PurePosixPath(relative_path)
    if path.is_symlink() or not path.is_file():
        raise LiveTypedSourceManifestError(f"source file must be a regular file: {path}")
    resolved = path.resolve()
    if not resolved.is_relative_to(directory):
        raise LiveTypedSourceManifestError("source file escapes snapshot directory")
    content = path.read_bytes()
    return SourceFileBinding(
        relative_path=relative_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _require_safe_relative_path(value: str, field: str) -> None:
    _require_text(value, field)
    path = PurePosixPath(value)
    unsafe_parts = any(part in {"", ".", ".."} for part in path.parts)
    if path.is_absolute() or value != path.as_posix() or unsafe_parts:
        raise ValueError(f"{field} must be a normalized safe relative POSIX path")


def _load_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LiveTypedSourceManifestError(f"JSON source must be a regular file: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveTypedSourceManifestError(f"cannot load JSON object: {path}") from exc
    return _object(raw, "JSON payload")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LiveTypedSourceManifestError(f"{field} must be a JSON object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _require_exact_fields(payload: dict[str, Any], expected: set[str], field: str) -> None:
    observed = set(payload)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise LiveTypedSourceManifestError(
            f"{field} fields mismatch; missing={missing}, unknown={unknown}"
        )


def _required_text(payload: dict[str, Any], field: str) -> str:
    if field not in payload:
        raise LiveTypedSourceManifestError(f"missing field: {field}")
    return _text(payload[field], field)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveTypedSourceManifestError(f"{field} must be non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveTypedSourceManifestError(f"{field} must be an integer")
    return value


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _parse_aware_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LiveTypedSourceManifestError(f"{field} must be an ISO datetime") from exc
    _require_aware(parsed, field)
    return parsed


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LiveTypedSourceManifestError(f"{field} must be an ISO date") from exc


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return _parse_date(_text(value, "evaluation_date"), "evaluation_date")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "FrozenSourceSnapshot",
    "LiveTypedSourceManifest",
    "LiveTypedSourceManifestError",
    "SourceFileBinding",
    "freeze_live_typed_source_manifest",
    "load_live_typed_source_manifest",
    "persist_live_typed_source_manifest",
    "verify_live_typed_source_manifest",
]
