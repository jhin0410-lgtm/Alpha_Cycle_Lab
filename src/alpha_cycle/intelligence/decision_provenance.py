"""Content-addressed market provenance envelopes for decision snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)

ENVELOPE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DecisionEvidenceEnvelope:
    """Bind one decision snapshot to its independently verified market evidence."""

    captured_at: datetime
    decision_snapshot_id: str
    decision_directory: str
    market_snapshot_id: str
    consistency: MarketConsistencyProvenance | None
    warnings: tuple[str, ...]

    @property
    def market_provenance_status(self) -> str:
        if self.consistency is None:
            return "not_connected"
        return self.consistency.mode

    @property
    def reference_price_cross_provider_certified(self) -> bool:
        return bool(self.consistency and self.consistency.live_price_certified)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "decision_snapshot_id": self.decision_snapshot_id,
            "decision_directory": self.decision_directory,
            "market_snapshot_id": self.market_snapshot_id,
            "market_provenance_status": self.market_provenance_status,
            "historical_market_evidence_verified": bool(
                self.consistency and self.consistency.historical_verified
            ),
            "reference_price_cross_provider_certified": (
                self.reference_price_cross_provider_certified
            ),
            "decision_integration_eligible": bool(
                self.consistency and self.consistency.decision_integration_eligible
            ),
            "consistency": (
                None if self.consistency is None else self.consistency.payload()
            ),
            "warnings": list(self.warnings),
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        }

    @property
    def envelope_id(self) -> str:
        canonical = json.dumps(
            self.payload_without_id(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _manifest(directory: Path) -> dict[str, object]:
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Decision manifest must be a JSON object")
    return cast(dict[str, object], payload)


def build_decision_evidence_envelope(
    decision_directory: str | Path,
    *,
    decision_snapshot_id: str,
    market_snapshot_id: str,
    consistency: MarketConsistencyProvenance | None,
    now: datetime | None = None,
) -> DecisionEvidenceEnvelope:
    """Create a fail-closed envelope without mutating the decision snapshot."""

    directory = Path(decision_directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError(f"Decision directory does not exist: {directory}")
    manifest = _manifest(directory)
    if str(manifest.get("snapshot_id", "")) != decision_snapshot_id:
        raise ValueError("Decision manifest snapshot_id does not match")
    if str(manifest.get("market_snapshot_id", "")) != market_snapshot_id:
        raise ValueError("Decision manifest market_snapshot_id does not match")
    if consistency is not None and consistency.market_snapshot_id != market_snapshot_id:
        raise ValueError("Market consistency evidence belongs to a different snapshot")

    warnings: list[str] = []
    if consistency is None:
        warnings.append("market_consistency_not_connected")
    elif consistency.live_price_certified:
        warnings.append("market_consistency_live_price_certified")
    else:
        warnings.append(
            "market_consistency_historical_only_reference_price_not_certified"
        )
    if consistency is not None:
        warnings.extend(consistency.warnings)
    return DecisionEvidenceEnvelope(
        captured_at=now or datetime.now(UTC),
        decision_snapshot_id=decision_snapshot_id,
        decision_directory=str(directory),
        market_snapshot_id=market_snapshot_id,
        consistency=consistency,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _report(envelope: DecisionEvidenceEnvelope) -> str:
    lines = [
        "# Alpha Cycle 결정 증거 Envelope",
        "",
        f"- Envelope ID: `{envelope.envelope_id}`",
        f"- Decision snapshot ID: `{envelope.decision_snapshot_id}`",
        f"- Market snapshot ID: `{envelope.market_snapshot_id}`",
        f"- 시장 provenance 상태: `{envelope.market_provenance_status}`",
        "- 과거 OHLC 교차검증: "
        + (
            "검증됨"
            if envelope.consistency and envelope.consistency.historical_verified
            else "미검증"
        ),
        "- 현재 기준가격 교차검증: "
        + (
            "인증됨"
            if envelope.reference_price_cross_provider_certified
            else "인증되지 않음"
        ),
        "- 공급자 자동 대체: 비활성",
        "- 계좌 API: 비활성",
        "- 주문 API: 비활성",
    ]
    if envelope.consistency is not None:
        lines.extend(
            [
                "",
                "## 연결된 시장 일관성 증거",
                "",
                f"- Assessment ID: `{envelope.consistency.assessment_id}`",
                f"- Raw result ID: `{envelope.consistency.result_id}`",
                f"- Raw status: `{envelope.consistency.raw_status}`",
                f"- Classification: `{envelope.consistency.classification}`",
                f"- Live quote status: `{envelope.consistency.live_quote_status}`",
            ]
        )
    if envelope.warnings:
        lines.extend(["", "## 경고", ""])
        lines.extend(f"- {warning}" for warning in envelope.warnings)
    return "\n".join(lines) + "\n"


def write_decision_evidence_envelope(
    output_root: str | Path,
    envelope: DecisionEvidenceEnvelope,
) -> tuple[Path, Path]:
    """Atomically write one immutable decision-market evidence envelope."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = envelope.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{envelope.envelope_id[:12]}"
    manifest_path = directory / "manifest.json"
    report_path = directory / "report.md"
    if directory.exists():
        existing = _manifest(directory)
        if existing.get("envelope_id") != envelope.envelope_id:
            raise ValueError("Existing decision evidence envelope conflicts")
        return manifest_path, report_path

    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        manifest = {
            **envelope.payload_without_id(),
            "envelope_id": envelope.envelope_id,
            "files": ["report.md"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "report.md").write_text(_report(envelope), encoding="utf-8")
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return manifest_path, report_path


__all__ = [
    "DecisionEvidenceEnvelope",
    "build_decision_evidence_envelope",
    "write_decision_evidence_envelope",
]
