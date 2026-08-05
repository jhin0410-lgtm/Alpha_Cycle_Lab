"""Tests for staged decision and provenance publication."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_provenance import (
    DecisionEvidenceEnvelope,
    write_decision_evidence_envelope,
)
from alpha_cycle.intelligence.decision_publication import (
    publish_decision_with_evidence,
)

SNAPSHOT_ID = "d" * 64
MARKET_ID = "b" * 64
DIRECTORY_NAME = "20260805T050000000000Z__dddddddddddd"


def _snapshot() -> InvestmentDecisionSnapshot:
    return cast(
        InvestmentDecisionSnapshot,
        SimpleNamespace(
            snapshot_id=SNAPSHOT_ID,
            market_snapshot_id=MARKET_ID,
        ),
    )


def _decision_writer(
    root: str | Path,
    snapshot: InvestmentDecisionSnapshot,
) -> tuple[Path, ...]:
    directory = Path(root) / DIRECTORY_NAME
    directory.mkdir(parents=True)
    manifest = directory / "manifest.json"
    report = directory / "report.md"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_id": snapshot.snapshot_id,
                "market_snapshot_id": snapshot.market_snapshot_id,
            }
        ),
        encoding="utf-8",
    )
    report.write_text("decision", encoding="utf-8")
    return manifest, report


def test_envelope_failure_does_not_publish_decision_snapshot(tmp_path: Path) -> None:
    decision_root = tmp_path / "decisions"
    provenance_root = tmp_path / "provenance"

    def failing_envelope_writer(
        _root: str | Path,
        _envelope: DecisionEvidenceEnvelope,
    ) -> tuple[Path, Path]:
        raise OSError("simulated envelope write failure")

    with pytest.raises(OSError, match="simulated envelope"):
        publish_decision_with_evidence(
            decision_output_root=decision_root,
            provenance_output_root=provenance_root,
            snapshot=_snapshot(),
            consistency=None,
            now=datetime(2026, 8, 5, 5, tzinfo=UTC),
            decision_writer=_decision_writer,
            envelope_writer=failing_envelope_writer,
        )

    assert not (decision_root / DIRECTORY_NAME).exists()
    assert not list(decision_root.glob(".decision-publication-*"))
    assert not list(provenance_root.glob(".decision-provenance-*"))


def test_success_publishes_envelope_before_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from alpha_cycle.intelligence import decision_publication as publication_module

    decision_root = tmp_path / "decisions"
    provenance_root = tmp_path / "provenance"
    order: list[str] = []
    original_publish = publication_module._publish_directory

    def recording_publish(
        source: Path,
        destination: Path,
        *,
        validator: Callable[[Path], bool],
        label: str,
    ) -> None:
        order.append(label)
        original_publish(
            source,
            destination,
            validator=validator,
            label=label,
        )

    monkeypatch.setattr(
        publication_module,
        "_publish_directory",
        recording_publish,
    )
    published = publish_decision_with_evidence(
        decision_output_root=decision_root,
        provenance_output_root=provenance_root,
        snapshot=_snapshot(),
        consistency=None,
        now=datetime(2026, 8, 5, 5, tzinfo=UTC),
        decision_writer=_decision_writer,
        envelope_writer=write_decision_evidence_envelope,
    )

    assert order == ["decision evidence envelope", "decision snapshot"]
    assert all(path.is_file() for path in published.decision_files)
    assert all(path.is_file() for path in published.envelope_files)
    envelope_manifest = json.loads(
        published.envelope_files[0].read_text(encoding="utf-8")
    )
    assert envelope_manifest["decision_directory"] == str(
        published.decision_files[0].parent.resolve()
    )
    assert published.envelope.decision_directory == str(
        published.decision_files[0].parent.resolve()
    )


def test_direct_cli_validates_consistency_before_publication() -> None:
    source = Path("src/alpha_cycle/decision_cli.py").read_text(encoding="utf-8")

    validation = source.index("load_market_consistency_provenance(")
    publication = source.index("publish_decision_with_evidence(")
    assert validation < publication
    assert "write_investment_decision_snapshot(args.output" not in source
