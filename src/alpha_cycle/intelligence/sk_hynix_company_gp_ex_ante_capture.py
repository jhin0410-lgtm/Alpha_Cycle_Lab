"""Append-only prospective source capture for SK hynix ex-ante forecasting.

Revision-prone data becomes prospective PIT evidence only when the exact source bytes are
captured and SHA-256 bound by the frozen forecast origin. This module never reads targets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    ExAnteFeatureFrontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    FrozenCompanyGPExAnteProtocol,
)

DEFAULT_EX_ANTE_CAPTURE_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-pit-capture"
)
_CAPTURE_LEDGER_NAME = "prospective_capture_ledger.json"


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True)
class ProspectiveCaptureReceipt:
    evidence_id: str
    protocol_evidence_id: str
    frontier_evidence_id: str
    sequence: int
    previous_receipt_evidence_id: str | None
    period_id: str
    feature_id: str
    source_id: str
    source_available_at: datetime
    captured_at: datetime
    source_bytes_sha256: str
    archive_relative_path: str
    observation_reference: str
    eligible_for_frozen_origin: bool
    target_read: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.protocol_evidence_id,
            self.frontier_evidence_id,
            self.source_bytes_sha256,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Prospective capture hashes must be SHA-256")
        if self.previous_receipt_evidence_id is not None and not _valid_sha(
            self.previous_receipt_evidence_id
        ):
            raise ValueError("Prospective capture previous receipt hash is invalid")
        if self.sequence <= 0:
            raise ValueError("Prospective capture sequence must be positive")
        if not self.period_id or not self.feature_id or not self.source_id:
            raise ValueError("Prospective capture identity fields are required")
        if not self.archive_relative_path or not self.observation_reference:
            raise ValueError("Prospective capture archive/reference fields are required")
        _aware(self.source_available_at, "source_available_at")
        _aware(self.captured_at, "captured_at")
        if self.source_available_at > self.captured_at:
            raise ValueError("Prospective capture cannot precede source availability")
        if self.target_read:
            raise ValueError("Prospective source capture cannot read target values")


@dataclass(frozen=True)
class ProspectiveCaptureLedger:
    protocol_evidence_id: str
    frontier_evidence_id: str
    receipts: tuple[ProspectiveCaptureReceipt, ...]

    def __post_init__(self) -> None:
        if not _valid_sha(self.protocol_evidence_id) or not _valid_sha(
            self.frontier_evidence_id
        ):
            raise ValueError("Prospective capture ledger evidence ids must be SHA-256")
        previous: str | None = None
        for expected_sequence, receipt in enumerate(self.receipts, start=1):
            if receipt.protocol_evidence_id != self.protocol_evidence_id:
                raise ValueError("Prospective capture protocol binding drifted")
            if receipt.frontier_evidence_id != self.frontier_evidence_id:
                raise ValueError("Prospective capture frontier binding drifted")
            if receipt.sequence != expected_sequence:
                raise ValueError("Prospective capture sequence is not contiguous")
            if receipt.previous_receipt_evidence_id != previous:
                raise ValueError("Prospective capture hash chain is broken")
            previous = receipt.evidence_id


def _receipt_stable_payload(receipt: ProspectiveCaptureReceipt) -> dict[str, object]:
    payload = asdict(receipt)
    payload.pop("evidence_id")
    payload["source_available_at"] = receipt.source_available_at.isoformat()
    payload["captured_at"] = receipt.captured_at.isoformat()
    return payload


def _receipt_from_mapping(payload: dict[str, object]) -> ProspectiveCaptureReceipt:
    try:
        source_available_at = datetime.fromisoformat(
            str(payload.get("source_available_at", ""))
        )
        captured_at = datetime.fromisoformat(str(payload.get("captured_at", "")))
    except ValueError as exc:
        raise ValueError("Prospective capture timestamps are invalid") from exc
    previous_raw = payload.get("previous_receipt_evidence_id")
    previous = None if previous_raw in {None, ""} else str(previous_raw)
    receipt = ProspectiveCaptureReceipt(
        evidence_id=str(payload.get("evidence_id", "")),
        protocol_evidence_id=str(payload.get("protocol_evidence_id", "")),
        frontier_evidence_id=str(payload.get("frontier_evidence_id", "")),
        sequence=int(str(payload.get("sequence", 0))),
        previous_receipt_evidence_id=previous,
        period_id=str(payload.get("period_id", "")),
        feature_id=str(payload.get("feature_id", "")),
        source_id=str(payload.get("source_id", "")),
        source_available_at=source_available_at,
        captured_at=captured_at,
        source_bytes_sha256=str(payload.get("source_bytes_sha256", "")),
        archive_relative_path=str(payload.get("archive_relative_path", "")),
        observation_reference=str(payload.get("observation_reference", "")),
        eligible_for_frozen_origin=(
            payload.get("eligible_for_frozen_origin") is True
        ),
        target_read=payload.get("target_read") is True,
    )
    if _sha_payload(_receipt_stable_payload(receipt)) != receipt.evidence_id:
        raise ValueError("Prospective capture receipt evidence hash mismatch")
    return receipt


def load_prospective_capture_ledger(
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    *,
    output_root: str | Path = DEFAULT_EX_ANTE_CAPTURE_OUTPUT,
    verify_blobs: bool = True,
) -> ProspectiveCaptureLedger:
    root = Path(output_root)
    ledger_path = root / _CAPTURE_LEDGER_NAME
    if not ledger_path.exists():
        return ProspectiveCaptureLedger(
            protocol_evidence_id=protocol.evidence_id,
            frontier_evidence_id=frontier.evidence_id,
            receipts=(),
        )
    raw: object = json.loads(ledger_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Prospective capture ledger must be an object")
    wrapper = {str(key): value for key, value in cast(dict[object, object], raw).items()}
    if wrapper.get("schema_version") != 1:
        raise ValueError("Prospective capture ledger schema is invalid")
    if wrapper.get("status") != "skhynix_ex_ante_prospective_capture_ledger":
        raise ValueError("Prospective capture ledger status is invalid")
    if str(wrapper.get("protocol_evidence_id", "")) != protocol.evidence_id:
        raise ValueError("Prospective capture ledger protocol evidence drifted")
    if str(wrapper.get("frontier_evidence_id", "")) != frontier.evidence_id:
        raise ValueError("Prospective capture ledger frontier evidence drifted")
    raw_receipts = wrapper.get("receipts")
    if not isinstance(raw_receipts, list):
        raise ValueError("Prospective capture ledger receipts must be an array")
    receipts: list[ProspectiveCaptureReceipt] = []
    for raw_receipt in raw_receipts:
        if not isinstance(raw_receipt, dict):
            raise ValueError("Prospective capture receipt must be an object")
        payload = {
            str(key): value
            for key, value in cast(dict[object, object], raw_receipt).items()
        }
        receipt = _receipt_from_mapping(payload)
        if verify_blobs:
            blob_path = root / receipt.archive_relative_path
            try:
                blob = blob_path.read_bytes()
            except FileNotFoundError as exc:
                raise ValueError(
                    f"Prospective capture blob is missing: {receipt.archive_relative_path}"
                ) from exc
            if _sha_bytes(blob) != receipt.source_bytes_sha256:
                raise ValueError("Prospective capture blob SHA-256 mismatch")
        receipts.append(receipt)
    return ProspectiveCaptureLedger(
        protocol_evidence_id=protocol.evidence_id,
        frontier_evidence_id=frontier.evidence_id,
        receipts=tuple(receipts),
    )


def _persist_ledger(
    ledger: ProspectiveCaptureLedger,
    output_root: Path,
) -> Path:
    path = output_root / _CAPTURE_LEDGER_NAME
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_ex_ante_prospective_capture_ledger",
        "protocol_evidence_id": ledger.protocol_evidence_id,
        "frontier_evidence_id": ledger.frontier_evidence_id,
        "receipt_count": len(ledger.receipts),
        "receipts": [asdict(item) for item in ledger.receipts],
        "target_read": False,
    }
    _write_json(path, payload)
    return path


def capture_prospective_source_bytes(
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    *,
    period_id: str,
    feature_id: str,
    source_id: str,
    source_available_at: datetime,
    raw_bytes: bytes,
    observation_reference: str,
    output_root: str | Path = DEFAULT_EX_ANTE_CAPTURE_OUTPUT,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[ProspectiveCaptureReceipt, bool]:
    """Capture exact source bytes and return ``(receipt, reused_existing)``."""

    _aware(source_available_at, "source_available_at")
    captured_at = now()
    _aware(captured_at, "capture clock")
    if source_available_at > captured_at:
        raise ValueError("Prospective capture source is not yet available")
    if period_id not in set(protocol.development_periods) | {
        *protocol.contaminated_report_only_periods,
        "2026Q3",
        "2026Q4",
    }:
        raise ValueError(f"Prospective capture period is unsupported: {period_id}")
    feature = frontier.by_id().get(feature_id)
    if feature is None:
        raise ValueError(f"Prospective capture feature is not registered: {feature_id}")
    if not feature.prospective_capture_eligible:
        raise ValueError(f"Feature is not prospective-capture eligible: {feature_id}")
    if not raw_bytes:
        raise ValueError("Prospective capture source bytes cannot be empty")
    if not source_id.strip() or not observation_reference.strip():
        raise ValueError("Prospective capture source identity/reference is required")

    root = Path(output_root)
    ledger = load_prospective_capture_ledger(
        protocol,
        frontier,
        output_root=root,
        verify_blobs=True,
    )
    source_sha = _sha_bytes(raw_bytes)
    for receipt in ledger.receipts:
        if (
            receipt.period_id == period_id
            and receipt.feature_id == feature_id
            and receipt.source_bytes_sha256 == source_sha
            and receipt.source_id == source_id
        ):
            return receipt, True

    blob_relative = Path("blobs") / f"{source_sha}.bin"
    blob_path = root / blob_relative
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    if blob_path.exists():
        if _sha_bytes(blob_path.read_bytes()) != source_sha:
            raise ValueError("Existing prospective capture blob hash mismatch")
    else:
        temporary = blob_path.with_name(f".{blob_path.name}.tmp")
        temporary.write_bytes(raw_bytes)
        temporary.replace(blob_path)

    previous = ledger.receipts[-1].evidence_id if ledger.receipts else None
    origin = protocol.origin_for(period_id)
    stable: dict[str, object] = {
        "protocol_evidence_id": protocol.evidence_id,
        "frontier_evidence_id": frontier.evidence_id,
        "sequence": len(ledger.receipts) + 1,
        "previous_receipt_evidence_id": previous,
        "period_id": period_id,
        "feature_id": feature_id,
        "source_id": source_id,
        "source_available_at": source_available_at.isoformat(),
        "captured_at": captured_at.isoformat(),
        "source_bytes_sha256": source_sha,
        "archive_relative_path": blob_relative.as_posix(),
        "observation_reference": observation_reference,
        "eligible_for_frozen_origin": (
            source_available_at <= origin and captured_at <= origin
        ),
        "target_read": False,
    }
    receipt = ProspectiveCaptureReceipt(
        evidence_id=_sha_payload(stable),
        protocol_evidence_id=protocol.evidence_id,
        frontier_evidence_id=frontier.evidence_id,
        sequence=len(ledger.receipts) + 1,
        previous_receipt_evidence_id=previous,
        period_id=period_id,
        feature_id=feature_id,
        source_id=source_id,
        source_available_at=source_available_at,
        captured_at=captured_at,
        source_bytes_sha256=source_sha,
        archive_relative_path=blob_relative.as_posix(),
        observation_reference=observation_reference,
        eligible_for_frozen_origin=(
            source_available_at <= origin and captured_at <= origin
        ),
    )
    updated = ProspectiveCaptureLedger(
        protocol_evidence_id=protocol.evidence_id,
        frontier_evidence_id=frontier.evidence_id,
        receipts=ledger.receipts + (receipt,),
    )
    _persist_ledger(updated, root)
    return receipt, False


__all__ = [
    "DEFAULT_EX_ANTE_CAPTURE_OUTPUT",
    "ProspectiveCaptureLedger",
    "ProspectiveCaptureReceipt",
    "capture_prospective_source_bytes",
    "load_prospective_capture_ledger",
]
