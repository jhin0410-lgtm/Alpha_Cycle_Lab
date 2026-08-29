"""Classify SK hynix cycle-driver magnitude text without inventing numeric inputs.

The structural rank probe deliberately uses only direction signs.  This diagnostic is the
next trust-boundary step: it inventories the magnitude language preserved in the verified
rank-probe rows and records only syntax that is literally present in the issuer text.

A number parsed from ``Around 20%`` or ``Over 70%`` is a text token, not an observed
numeric driver value.  Linguistic bands such as ``Mid-high-teen%`` remain labels, and
qualitative phrases such as ``Slight`` remain qualitative.  No midpoint, interval width,
or measurement-error distribution is inferred here, so fitting stays disabled.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
    DirectionSignEncoding,
    StructuralRankProbeResult,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    load_structural_rank_probe_report,
)

DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-magnitude-descriptor-diagnostic"
)
DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_POINTER = (
    DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT
    / "latest_magnitude_descriptor_diagnostic.json"
)

_DRIVER_NAMES = (
    "dram_asp",
    "dram_bit_volume",
    "nand_asp",
    "nand_bit_volume",
)
_ALLOWED_KINDS = frozenset(
    {
        "flat_direction_only",
        "literal_percent_text",
        "approximate_percent_anchor",
        "lower_threshold_percent",
        "linguistic_percent_band",
        "qualitative_only",
        "unclassified",
    }
)
_ALLOWED_BLOCK_REASONS = frozenset(
    {
        "rank_probe_not_ready",
        "unclassified_magnitude_descriptors",
        "measurement_error_encoding_not_registered",
    }
)
_AROUND_PERCENT = re.compile(r"^Around\s+(\d+(?:\.\d+)?)%$", re.IGNORECASE)
_OVER_PERCENT = re.compile(r"^Over\s+(\d+(?:\.\d+)?)%$", re.IGNORECASE)
_LITERAL_PERCENT = re.compile(r"^(\d+(?:\.\d+)?)%$")
_LINGUISTIC_PERCENT = re.compile(r"^[A-Za-z]+(?:-[A-Za-z0-9]+)+%$")


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class MagnitudeDescriptorObservation:
    period_id: str
    driver_name: str
    source_text: str
    direction: str
    magnitude_phrase: str
    descriptor_kind: str
    numeric_token_percent: float | None
    linguistic_band_label: str | None
    numeric_driver_source_fact: bool = False
    model_numeric_value_assigned: bool = False
    estimation_input_ready: bool = False

    def __post_init__(self) -> None:
        if not self.period_id or self.driver_name not in _DRIVER_NAMES:
            raise ValueError("Magnitude descriptor observation identity is invalid")
        if self.direction not in {"increase", "flat", "decrease"}:
            raise ValueError("Magnitude descriptor direction is invalid")
        if self.descriptor_kind not in _ALLOWED_KINDS:
            raise ValueError("Magnitude descriptor kind is invalid")
        if self.source_text != " ".join(self.source_text.split()) or not self.source_text:
            raise ValueError("Magnitude descriptor source text must be normalized")
        if self.numeric_token_percent is not None:
            if self.numeric_token_percent < 0:
                raise ValueError("Magnitude descriptor numeric text token cannot be negative")
            if self.descriptor_kind not in {
                "literal_percent_text",
                "approximate_percent_anchor",
                "lower_threshold_percent",
            }:
                raise ValueError("Magnitude descriptor numeric token is attached to wrong kind")
        if self.linguistic_band_label is not None:
            if self.descriptor_kind != "linguistic_percent_band":
                raise ValueError("Magnitude descriptor band label is attached to wrong kind")
            if self.linguistic_band_label != self.magnitude_phrase:
                raise ValueError("Magnitude descriptor band label must preserve source text")
        if (
            self.numeric_driver_source_fact
            or self.model_numeric_value_assigned
            or self.estimation_input_ready
        ):
            raise ValueError("Magnitude descriptor diagnostic exceeds its trust boundary")


@dataclass(frozen=True)
class MagnitudeDescriptorDiagnosticResult:
    evidence_id: str
    evaluation_date: date
    source_rank_probe_evidence_id: str
    source_rank_probe_pointer_sha256: str
    method_id: str
    method_version: str
    training_periods: tuple[str, ...]
    observations: tuple[MagnitudeDescriptorObservation, ...]
    observation_count: int
    unique_source_text_count: int
    descriptor_kind_counts: tuple[tuple[str, int], ...]
    numeric_token_observation_count: int
    unclassified_source_texts: tuple[str, ...]
    rank_probe_ready: bool
    all_descriptors_classified: bool
    measurement_error_encoding_registered: bool
    numeric_driver_source_facts_available: bool
    model_numeric_values_assigned: bool
    estimation_inputs_ready: bool
    fit_attempt_allowed: bool
    holdout_evaluation_allowed: bool
    block_reason: str
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(
            self.source_rank_probe_evidence_id
        ) or not _valid_sha(self.source_rank_probe_pointer_sha256):
            raise ValueError("Magnitude descriptor diagnostic evidence hashes must be SHA-256")
        if self.observation_count != len(self.observations):
            raise ValueError("Magnitude descriptor observation count is inconsistent")
        if self.training_periods != tuple(
            dict.fromkeys(item.period_id for item in self.observations)
        ):
            raise ValueError("Magnitude descriptor training-period binding is inconsistent")
        expected_unique = len({item.source_text for item in self.observations})
        if self.unique_source_text_count != expected_unique:
            raise ValueError("Magnitude descriptor unique-text count is inconsistent")
        expected_counts = tuple(
            (kind, sum(item.descriptor_kind == kind for item in self.observations))
            for kind in sorted(_ALLOWED_KINDS)
            if any(item.descriptor_kind == kind for item in self.observations)
        )
        if self.descriptor_kind_counts != expected_counts:
            raise ValueError("Magnitude descriptor kind counts are inconsistent")
        expected_numeric_tokens = sum(
            item.numeric_token_percent is not None for item in self.observations
        )
        if self.numeric_token_observation_count != expected_numeric_tokens:
            raise ValueError("Magnitude descriptor numeric-token count is inconsistent")
        expected_unclassified = tuple(
            sorted(
                {
                    item.source_text
                    for item in self.observations
                    if item.descriptor_kind == "unclassified"
                }
            )
        )
        if self.unclassified_source_texts != expected_unclassified:
            raise ValueError("Magnitude descriptor unclassified-text inventory is inconsistent")
        if self.all_descriptors_classified != (not expected_unclassified):
            raise ValueError("Magnitude descriptor classification readiness is inconsistent")
        if self.block_reason not in _ALLOWED_BLOCK_REASONS:
            raise ValueError("Magnitude descriptor diagnostic block reason is invalid")
        expected_reason = (
            "rank_probe_not_ready"
            if not self.rank_probe_ready
            else (
                "unclassified_magnitude_descriptors"
                if expected_unclassified
                else "measurement_error_encoding_not_registered"
            )
        )
        if self.block_reason != expected_reason:
            raise ValueError("Magnitude descriptor diagnostic block reason is inconsistent")
        if (
            self.measurement_error_encoding_registered
            or self.numeric_driver_source_facts_available
            or self.model_numeric_values_assigned
            or self.estimation_inputs_ready
            or self.fit_attempt_allowed
            or self.holdout_evaluation_allowed
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Magnitude descriptor diagnostic opened a forbidden gate")


def classify_magnitude_descriptor(
    *,
    period_id: str,
    driver_name: str,
    encoding: DirectionSignEncoding,
) -> MagnitudeDescriptorObservation:
    """Classify literal magnitude syntax while assigning no model magnitude."""

    text = " ".join(encoding.source_text.split())
    if encoding.direction == "flat":
        magnitude_phrase = "Flat"
        kind = "flat_direction_only"
        numeric_token: float | None = None
        band_label: str | None = None
    else:
        suffix = " Increase" if encoding.direction == "increase" else " Decrease"
        if not text.endswith(suffix):
            raise ValueError("Magnitude descriptor direction/source text binding diverged")
        magnitude_phrase = text[: -len(suffix)].strip()
        numeric_token = None
        band_label = None
        if match := _AROUND_PERCENT.fullmatch(magnitude_phrase):
            kind = "approximate_percent_anchor"
            numeric_token = float(match.group(1))
        elif match := _OVER_PERCENT.fullmatch(magnitude_phrase):
            kind = "lower_threshold_percent"
            numeric_token = float(match.group(1))
        elif match := _LITERAL_PERCENT.fullmatch(magnitude_phrase):
            kind = "literal_percent_text"
            numeric_token = float(match.group(1))
        elif _LINGUISTIC_PERCENT.fullmatch(magnitude_phrase):
            kind = "linguistic_percent_band"
            band_label = magnitude_phrase
        elif magnitude_phrase.casefold() == "slight":
            kind = "qualitative_only"
        else:
            kind = "unclassified"

    return MagnitudeDescriptorObservation(
        period_id=period_id,
        driver_name=driver_name,
        source_text=text,
        direction=encoding.direction,
        magnitude_phrase=magnitude_phrase,
        descriptor_kind=kind,
        numeric_token_percent=numeric_token,
        linguistic_band_label=band_label,
    )


def build_magnitude_descriptor_diagnostic(
    rank_probe: StructuralRankProbeResult,
    *,
    source_rank_probe_pointer_sha256: str,
) -> MagnitudeDescriptorDiagnosticResult:
    """Inventory rank-probe magnitude text while preserving the no-fit boundary."""

    if not _valid_sha(source_rank_probe_pointer_sha256):
        raise ValueError("Rank-probe pointer hash must be SHA-256")
    observations: list[MagnitudeDescriptorObservation] = []
    for row in rank_probe.rows:
        for driver_name in _DRIVER_NAMES:
            encoding = cast(DirectionSignEncoding, getattr(row, driver_name))
            observations.append(
                classify_magnitude_descriptor(
                    period_id=row.period_id,
                    driver_name=driver_name,
                    encoding=encoding,
                )
            )
    observation_tuple = tuple(observations)
    unclassified = tuple(
        sorted(
            {
                item.source_text
                for item in observation_tuple
                if item.descriptor_kind == "unclassified"
            }
        )
    )
    counts = tuple(
        (kind, sum(item.descriptor_kind == kind for item in observation_tuple))
        for kind in sorted(_ALLOWED_KINDS)
        if any(item.descriptor_kind == kind for item in observation_tuple)
    )
    numeric_tokens = sum(
        item.numeric_token_percent is not None for item in observation_tuple
    )
    if not rank_probe.rank_probe_ready:
        block_reason = "rank_probe_not_ready"
    elif unclassified:
        block_reason = "unclassified_magnitude_descriptors"
    else:
        block_reason = "measurement_error_encoding_not_registered"

    stable_payload = {
        "evaluation_date": rank_probe.evaluation_date.isoformat(),
        "source_rank_probe_evidence_id": rank_probe.evidence_id,
        "source_rank_probe_pointer_sha256": source_rank_probe_pointer_sha256,
        "method_id": rank_probe.method_id,
        "method_version": rank_probe.method_version,
        "training_periods": rank_probe.training_periods,
        "observations": [asdict(item) for item in observation_tuple],
        "descriptor_kind_counts": counts,
        "numeric_token_observation_count": numeric_tokens,
        "unclassified_source_texts": unclassified,
        "rank_probe_ready": rank_probe.rank_probe_ready,
        "all_descriptors_classified": not unclassified,
        "measurement_error_encoding_registered": False,
        "numeric_driver_source_facts_available": False,
        "model_numeric_values_assigned": False,
        "estimation_inputs_ready": False,
        "fit_attempt_allowed": False,
        "holdout_evaluation_allowed": False,
        "block_reason": block_reason,
    }
    return MagnitudeDescriptorDiagnosticResult(
        evidence_id=_sha_payload(stable_payload),
        evaluation_date=rank_probe.evaluation_date,
        source_rank_probe_evidence_id=rank_probe.evidence_id,
        source_rank_probe_pointer_sha256=source_rank_probe_pointer_sha256,
        method_id=rank_probe.method_id,
        method_version=rank_probe.method_version,
        training_periods=rank_probe.training_periods,
        observations=observation_tuple,
        observation_count=len(observation_tuple),
        unique_source_text_count=len({item.source_text for item in observation_tuple}),
        descriptor_kind_counts=counts,
        numeric_token_observation_count=numeric_tokens,
        unclassified_source_texts=unclassified,
        rank_probe_ready=rank_probe.rank_probe_ready,
        all_descriptors_classified=not unclassified,
        measurement_error_encoding_registered=False,
        numeric_driver_source_facts_available=False,
        model_numeric_values_assigned=False,
        estimation_inputs_ready=False,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reason=block_reason,
    )


def magnitude_descriptor_diagnostic_payload(
    result: MagnitudeDescriptorDiagnosticResult,
) -> dict[str, object]:
    payload = asdict(result)
    payload["evaluation_date"] = result.evaluation_date.isoformat()
    normalized: object = json.loads(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    if not isinstance(normalized, dict):
        raise ValueError("Magnitude descriptor diagnostic payload must normalize to an object")
    return {str(key): value for key, value in cast(dict[object, object], normalized).items()}


def capture_magnitude_descriptor_diagnostic(
    *,
    evaluation_date: date,
    rank_probe_pointer: str | Path = DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
    output: str | Path = DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Snapshot the exact rank pointer and archive a deterministic descriptor inventory."""

    source_pointer = Path(rank_probe_pointer)
    try:
        pointer_bytes = source_pointer.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Structural rank-probe pointer not found: {source_pointer}") from exc
    pointer_sha = _sha_bytes(pointer_bytes)
    rank_probe = load_structural_rank_probe_report(
        source_pointer,
        evaluation_date=evaluation_date,
    )
    result = build_magnitude_descriptor_diagnostic(
        rank_probe,
        source_rank_probe_pointer_sha256=pointer_sha,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("Magnitude descriptor diagnostic captured_at must be timezone-aware")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + result.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Magnitude descriptor diagnostic artifact already exists: {directory}")
    directory.mkdir()
    rank_snapshot_path = directory / "rank_probe_pointer_snapshot.json"
    rank_snapshot_path.write_bytes(pointer_bytes)
    report_path = directory / "magnitude_descriptor_diagnostic.json"
    report = magnitude_descriptor_diagnostic_payload(result)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    pointer = {
        **report,
        "schema_version": 1,
        "status": "skhynix_product_profitability_magnitude_descriptor_diagnostic_captured",
        "captured_at": captured.isoformat(),
        "report_path": str(report_path.resolve()),
        "rank_probe_pointer_snapshot_path": str(rank_snapshot_path.resolve()),
    }
    pointer_path = root / "latest_magnitude_descriptor_diagnostic.json"
    temporary = root / ".latest_magnitude_descriptor_diagnostic.json.tmp"
    temporary.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def load_magnitude_descriptor_diagnostic(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> MagnitudeDescriptorDiagnosticResult:
    """Rebuild a diagnostic from its snapshotted rank-probe pointer and compare exactly."""

    pointer = _object(Path(pointer_path), "Magnitude descriptor diagnostic pointer")
    if (
        pointer.get("status")
        != "skhynix_product_profitability_magnitude_descriptor_diagnostic_captured"
    ):
        raise ValueError("Magnitude descriptor diagnostic pointer status is invalid")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Magnitude descriptor diagnostic evaluation date mismatch")

    snapshot_path = Path(str(pointer.get("rank_probe_pointer_snapshot_path", "")))
    try:
        snapshot_bytes = snapshot_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Magnitude descriptor rank-probe pointer snapshot is missing") from exc
    pointer_sha = _sha_bytes(snapshot_bytes)
    if pointer_sha != str(pointer.get("source_rank_probe_pointer_sha256", "")):
        raise ValueError("Magnitude descriptor rank-probe pointer snapshot hash diverged")
    rank_probe = load_structural_rank_probe_report(
        snapshot_path,
        evaluation_date=evaluation_date,
    )
    reconstructed = build_magnitude_descriptor_diagnostic(
        rank_probe,
        source_rank_probe_pointer_sha256=pointer_sha,
    )
    expected = magnitude_descriptor_diagnostic_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"Magnitude descriptor diagnostic no longer reproduces: {key}")
    report = _object(
        Path(str(pointer.get("report_path", ""))),
        "Magnitude descriptor diagnostic report",
    )
    if report != expected:
        raise ValueError("Magnitude descriptor diagnostic report payload no longer reproduces")
    return reconstructed


__all__ = [
    "DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_OUTPUT",
    "DEFAULT_MAGNITUDE_DESCRIPTOR_DIAGNOSTIC_POINTER",
    "MagnitudeDescriptorDiagnosticResult",
    "MagnitudeDescriptorObservation",
    "build_magnitude_descriptor_diagnostic",
    "capture_magnitude_descriptor_diagnostic",
    "classify_magnitude_descriptor",
    "load_magnitude_descriptor_diagnostic",
    "magnitude_descriptor_diagnostic_payload",
]
