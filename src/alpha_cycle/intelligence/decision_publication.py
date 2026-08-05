"""Fail-closed publication of decisions and their market provenance envelopes."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.decision import (
    InvestmentDecisionSnapshot,
    write_investment_decision_snapshot,
)
from alpha_cycle.intelligence.decision_provenance import (
    DecisionEvidenceEnvelope,
    build_decision_evidence_envelope,
    write_decision_evidence_envelope,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)

DecisionWriter = Callable[
    [str | Path, InvestmentDecisionSnapshot],
    tuple[Path, ...],
]
EnvelopeWriter = Callable[
    [str | Path, DecisionEvidenceEnvelope],
    tuple[Path, Path],
]


class DecisionProvenancePublicationError(ValueError):
    """Envelope construction or publication failed after decision staging."""


@dataclass(frozen=True)
class PublishedDecisionEvidence:
    """Paths and envelope published as one fail-closed decision operation."""

    decision_files: tuple[Path, ...]
    envelope_files: tuple[Path, Path]
    envelope: DecisionEvidenceEnvelope


def _json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(dict[str, object], payload)


def _valid_decision_directory(
    directory: Path,
    *,
    snapshot_id: str,
    names: tuple[str, ...],
) -> bool:
    try:
        manifest = _json_object(directory / "manifest.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        manifest.get("snapshot_id") == snapshot_id
        and all((directory / name).is_file() for name in names)
    )


def _valid_envelope_directory(directory: Path, *, envelope_id: str) -> bool:
    try:
        manifest = _json_object(directory / "manifest.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        manifest.get("envelope_id") == envelope_id
        and (directory / "report.md").is_file()
    )


def _publish_directory(
    source: Path,
    destination: Path,
    *,
    validator: Callable[[Path], bool],
    label: str,
) -> None:
    if destination.exists():
        if not validator(destination):
            raise ValueError(f"Existing {label} conflicts with staged publication")
        return
    try:
        source.rename(destination)
    except OSError:
        if not validator(destination):
            raise


def publish_decision_with_evidence(
    *,
    decision_output_root: str | Path,
    provenance_output_root: str | Path,
    snapshot: InvestmentDecisionSnapshot,
    consistency: MarketConsistencyProvenance | None,
    now: datetime | None = None,
    decision_writer: DecisionWriter = write_investment_decision_snapshot,
    envelope_writer: EnvelopeWriter = write_decision_evidence_envelope,
) -> PublishedDecisionEvidence:
    """Publish an envelope first and expose the decision directory last.

    Decision writer and final decision-directory failures remain ordinary write
    failures. Only envelope construction or publication is reclassified as a
    provenance failure by the live and resume wrappers.
    """

    decision_root = Path(decision_output_root)
    provenance_root = Path(provenance_output_root)
    decision_root.mkdir(parents=True, exist_ok=True)
    provenance_root.mkdir(parents=True, exist_ok=True)
    decision_stage_root = Path(
        tempfile.mkdtemp(prefix=".decision-publication-", dir=decision_root)
    )
    provenance_stage_root = Path(
        tempfile.mkdtemp(prefix=".decision-provenance-", dir=provenance_root)
    )
    try:
        staged_decision_files = decision_writer(decision_stage_root, snapshot)
        if not staged_decision_files:
            raise ValueError("Decision writer returned no staged files")
        staged_decision_directory = staged_decision_files[0].parent
        decision_names = tuple(path.name for path in staged_decision_files)
        final_decision_directory = decision_root / staged_decision_directory.name

        def decision_validator(directory: Path) -> bool:
            return _valid_decision_directory(
                directory,
                snapshot_id=snapshot.snapshot_id,
                names=decision_names,
            )

        if final_decision_directory.exists() and not decision_validator(
            final_decision_directory
        ):
            raise ValueError("Existing decision snapshot conflicts with publication")

        try:
            envelope = build_decision_evidence_envelope(
                staged_decision_directory,
                decision_snapshot_id=snapshot.snapshot_id,
                market_snapshot_id=snapshot.market_snapshot_id,
                consistency=consistency,
                published_decision_directory=final_decision_directory,
                now=now,
            )
            staged_envelope_files = envelope_writer(provenance_stage_root, envelope)
            staged_envelope_directory = staged_envelope_files[0].parent
            final_envelope_directory = provenance_root / staged_envelope_directory.name

            def envelope_validator(directory: Path) -> bool:
                return _valid_envelope_directory(
                    directory,
                    envelope_id=envelope.envelope_id,
                )

            if final_envelope_directory.exists() and not envelope_validator(
                final_envelope_directory
            ):
                raise ValueError("Existing decision evidence envelope conflicts")
            _publish_directory(
                staged_envelope_directory,
                final_envelope_directory,
                validator=envelope_validator,
                label="decision evidence envelope",
            )
        except (OSError, TypeError, ValueError) as exc:
            raise DecisionProvenancePublicationError(
                f"Decision evidence envelope publication failed: {exc}"
            ) from exc

        _publish_directory(
            staged_decision_directory,
            final_decision_directory,
            validator=decision_validator,
            label="decision snapshot",
        )
        final_decision_files = tuple(
            final_decision_directory / name for name in decision_names
        )
        final_envelope_files = (
            final_envelope_directory / staged_envelope_files[0].name,
            final_envelope_directory / staged_envelope_files[1].name,
        )
        return PublishedDecisionEvidence(
            decision_files=final_decision_files,
            envelope_files=final_envelope_files,
            envelope=envelope,
        )
    finally:
        if decision_stage_root.exists():
            shutil.rmtree(decision_stage_root)
        if provenance_stage_root.exists():
            shutil.rmtree(provenance_stage_root)


__all__ = [
    "DecisionProvenancePublicationError",
    "PublishedDecisionEvidence",
    "publish_decision_with_evidence",
]
