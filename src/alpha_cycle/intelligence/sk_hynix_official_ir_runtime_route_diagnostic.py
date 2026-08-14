"""Offline diagnostic for runtime data routes in archived SK hynix IR page/JavaScript bytes.

The official Earnings Release page can expose no literal PDF URL while still loading the
attachment metadata at runtime.  This module never guesses an endpoint and never performs
network I/O.  It first reverifies the source attachment-discovery artifact, then inspects
only the archived official page and issuer-controlled JavaScript bytes for literal network
call sites, endpoint-like strings, and attachment/download-related contexts.

The output is diagnostic evidence only.  A discovered route string is not an authorized
API call and cannot activate a product baseline, allocation resolver, forecast, score, or
trade path.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery_verifier import (
    load_official_ir_attachment_discovery_evidence,
)

DEFAULT_RUNTIME_ROUTE_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-runtime-route-diagnostic"
)
DEFAULT_RUNTIME_ROUTE_POINTER = (
    DEFAULT_RUNTIME_ROUTE_OUTPUT / "latest_skhynix_ir_runtime_route_diagnostic.json"
)

_MAX_CONTEXT_CHARS = 280
_MAX_STRING_CHARS = 420
_MAX_SIGNALS_PER_KIND_PER_SOURCE = 12

_NETWORK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fetch", re.compile(r"\bfetch\s*\(", flags=re.IGNORECASE)),
    ("axios", re.compile(r"\baxios(?:\.[A-Za-z_$][\w$]*)?\s*\(", flags=re.IGNORECASE)),
    ("xml_http_request", re.compile(r"\b(?:new\s+)?XMLHttpRequest\b", flags=re.IGNORECASE)),
    ("jquery_ajax", re.compile(r"\$\.(?:ajax|get|post|getJSON)\s*\(", flags=re.IGNORECASE)),
)
_RUNTIME_TOKENS = (
    "attach",
    "attachment",
    "download",
    "file",
    "api",
    "ajax",
    "earnings",
    "release",
    "ir06",
    "board",
    "blob",
)
_QUOTED_LITERAL = re.compile(r"(?P<quote>['\"`])(?P<value>[^'\"`\r\n]{1,420})(?P=quote)")
_PATHISH_PREFIXES = ("/", "./", "../", "http://", "https://")
_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


@dataclass(frozen=True)
class RuntimeRouteSignal:
    source_file: str
    source_url: str
    kind: str
    token: str
    literal: str | None
    context: str


@dataclass(frozen=True)
class RuntimeSourceSummary:
    source_file: str
    source_url: str
    source_sha256: str
    source_bytes: int
    network_call_site_count: int
    route_literal_count: int
    attachment_context_count: int


@dataclass(frozen=True)
class OfficialIrRuntimeRouteDiagnostic:
    evidence_id: str
    source_evidence_id: str
    observed_date: date
    source_summaries: tuple[RuntimeSourceSummary, ...]
    network_call_sites: tuple[RuntimeRouteSignal, ...]
    route_literals: tuple[RuntimeRouteSignal, ...]
    attachment_contexts: tuple[RuntimeRouteSignal, ...]
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.source_evidence_id):
            raise ValueError("SK hynix runtime-route diagnostic IDs must be SHA-256")
        if not self.source_summaries:
            raise ValueError("SK hynix runtime-route diagnostic requires archived sources")
        if not self.discovery_only:
            raise ValueError("SK hynix runtime-route diagnostic must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix runtime-route diagnostic cannot widen model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _normalized_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\\/", "/")


def _compact(value: str) -> str:
    return " ".join(value.split())


def _context(text: str, start: int, end: int) -> str:
    half = _MAX_CONTEXT_CHARS // 2
    left = max(0, start - half)
    right = min(len(text), end + half)
    return _compact(text[left:right])[:_MAX_CONTEXT_CHARS]


def _is_runtime_relevant_literal(value: str) -> bool:
    folded = value.casefold()
    if not any(token in folded for token in _RUNTIME_TOKENS):
        return False
    if value.startswith(_PATHISH_PREFIXES):
        return True
    return any(separator in value for separator in ("/", "?", "=", ".json", ".do", ".action"))


def _signal_payload(item: RuntimeRouteSignal) -> dict[str, object]:
    return {
        "source_file": item.source_file,
        "source_url": item.source_url,
        "kind": item.kind,
        "token": item.token,
        "literal": item.literal,
        "context": item.context,
    }


def _source_payload(item: RuntimeSourceSummary) -> dict[str, object]:
    return {
        "source_file": item.source_file,
        "source_url": item.source_url,
        "source_sha256": item.source_sha256,
        "source_bytes": item.source_bytes,
        "network_call_site_count": item.network_call_site_count,
        "route_literal_count": item.route_literal_count,
        "attachment_context_count": item.attachment_context_count,
    }


def scan_runtime_source(
    *,
    source_file: str,
    source_url: str,
    data: bytes,
) -> tuple[
    RuntimeSourceSummary,
    tuple[RuntimeRouteSignal, ...],
    tuple[RuntimeRouteSignal, ...],
    tuple[RuntimeRouteSignal, ...],
]:
    """Extract bounded, literal-only runtime-route signals from one archived source."""

    text = _normalized_text(data)
    network: list[RuntimeRouteSignal] = []
    route_literals: list[RuntimeRouteSignal] = []
    attachment_contexts: list[RuntimeRouteSignal] = []

    for kind, pattern in _NETWORK_PATTERNS:
        for match in pattern.finditer(text):
            if len(network) >= len(_NETWORK_PATTERNS) * _MAX_SIGNALS_PER_KIND_PER_SOURCE:
                break
            network.append(
                RuntimeRouteSignal(
                    source_file=source_file,
                    source_url=source_url,
                    kind="network_call_site",
                    token=kind,
                    literal=None,
                    context=_context(text, match.start(), match.end()),
                )
            )

    seen_literals: set[str] = set()
    for match in _QUOTED_LITERAL.finditer(text):
        raw = match.group("value")[:_MAX_STRING_CHARS]
        value = _compact(raw)
        if not value or value in seen_literals or not _is_runtime_relevant_literal(value):
            continue
        seen_literals.add(value)
        if len(route_literals) >= _MAX_SIGNALS_PER_KIND_PER_SOURCE:
            break
        token = next(
            (item for item in _RUNTIME_TOKENS if item in value.casefold()),
            "runtime_route",
        )
        route_literals.append(
            RuntimeRouteSignal(
                source_file=source_file,
                source_url=source_url,
                kind="route_literal",
                token=token,
                literal=value,
                context=_context(text, match.start(), match.end()),
            )
        )

    context_tokens = ("attach", "attachment", "download", "file", "earnings", "release")
    for token in context_tokens:
        pattern = re.compile(re.escape(token), flags=re.IGNORECASE)
        count_for_token = 0
        for match in pattern.finditer(text):
            if count_for_token >= _MAX_SIGNALS_PER_KIND_PER_SOURCE:
                break
            attachment_contexts.append(
                RuntimeRouteSignal(
                    source_file=source_file,
                    source_url=source_url,
                    kind="attachment_context",
                    token=token,
                    literal=None,
                    context=_context(text, match.start(), match.end()),
                )
            )
            count_for_token += 1

    summary = RuntimeSourceSummary(
        source_file=source_file,
        source_url=source_url,
        source_sha256=_sha_bytes(data),
        source_bytes=len(data),
        network_call_site_count=len(network),
        route_literal_count=len(route_literals),
        attachment_context_count=len(attachment_contexts),
    )
    return summary, tuple(network), tuple(route_literals), tuple(attachment_contexts)


def _load_verified_archived_sources(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> tuple[str, date, tuple[tuple[str, str, bytes], ...]]:
    pointer_file = Path(pointer_path)
    evidence = load_official_ir_attachment_discovery_evidence(
        pointer_file,
        evaluation_date=evaluation_date,
    )
    pointer = _json_object(pointer_file, "SK hynix IR attachment discovery pointer")
    if str(pointer.get("evidence_id", "")) != evidence.evidence_id:
        raise ValueError("SK hynix runtime diagnostic source evidence ID mismatch")
    artifact_directory = Path(str(pointer.get("artifact_directory", "")))
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SK hynix IR attachment discovery manifest",
    )
    page_bytes = (artifact_directory / "official_ir_page.html").read_bytes()
    if _sha_bytes(page_bytes) != evidence.ir_page_sha256:
        raise ValueError("SK hynix runtime diagnostic page hash mismatch")

    sources: list[tuple[str, str, bytes]] = [
        ("official_ir_page.html", str(pointer.get("ir_page_url", "")), page_bytes)
    ]
    raw_scripts = manifest.get("scripts")
    if not isinstance(raw_scripts, list):
        raise ValueError("SK hynix runtime diagnostic source manifest has invalid scripts")
    for raw in raw_scripts:
        if not isinstance(raw, dict):
            raise ValueError("SK hynix runtime diagnostic script row is invalid")
        row = cast(dict[object, object], raw)
        file_name = str(row.get("file", ""))
        script_url = str(row.get("url", ""))
        expected_sha = str(row.get("sha256", ""))
        if Path(file_name).name != file_name or not script_url:
            raise ValueError("SK hynix runtime diagnostic script identity is unsafe")
        data = (artifact_directory / file_name).read_bytes()
        if _sha_bytes(data) != expected_sha:
            raise ValueError("SK hynix runtime diagnostic archived script hash mismatch")
        sources.append((file_name, script_url, data))
    return evidence.evidence_id, evidence.observed_date, tuple(sources)


def build_runtime_route_diagnostic(
    pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrRuntimeRouteDiagnostic:
    source_evidence_id, observed_date, sources = _load_verified_archived_sources(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    summaries: list[RuntimeSourceSummary] = []
    network: list[RuntimeRouteSignal] = []
    route_literals: list[RuntimeRouteSignal] = []
    attachment_contexts: list[RuntimeRouteSignal] = []
    for file_name, source_url, data in sources:
        summary, source_network, source_routes, source_contexts = scan_runtime_source(
            source_file=file_name,
            source_url=source_url,
            data=data,
        )
        summaries.append(summary)
        network.extend(source_network)
        route_literals.extend(source_routes)
        attachment_contexts.extend(source_contexts)

    payload = {
        "source_evidence_id": source_evidence_id,
        "observed_date": observed_date.isoformat(),
        "source_summaries": [_source_payload(item) for item in summaries],
        "network_call_sites": [_signal_payload(item) for item in network],
        "route_literals": [_signal_payload(item) for item in route_literals],
        "attachment_contexts": [_signal_payload(item) for item in attachment_contexts],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrRuntimeRouteDiagnostic(
        evidence_id=_sha_payload(payload),
        source_evidence_id=source_evidence_id,
        observed_date=observed_date,
        source_summaries=tuple(summaries),
        network_call_sites=tuple(network),
        route_literals=tuple(route_literals),
        attachment_contexts=tuple(attachment_contexts),
    )


def _diagnostic_payload(evidence: OfficialIrRuntimeRouteDiagnostic) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_runtime_route_diagnostic_captured",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "source_count": len(evidence.source_summaries),
        "network_call_site_count": len(evidence.network_call_sites),
        "route_literal_count": len(evidence.route_literals),
        "attachment_context_count": len(evidence.attachment_contexts),
        "source_summaries": [_source_payload(item) for item in evidence.source_summaries],
        "network_call_sites": [_signal_payload(item) for item in evidence.network_call_sites],
        "route_literals": [_signal_payload(item) for item in evidence.route_literals],
        "attachment_contexts": [_signal_payload(item) for item in evidence.attachment_contexts],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def capture_runtime_route_diagnostic(
    pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_RUNTIME_ROUTE_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence = build_runtime_route_diagnostic(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix runtime-route diagnostic artifact path already exists")
    temporary.mkdir()
    try:
        payload = _diagnostic_payload(evidence)
        payload["captured_at"] = captured.isoformat()
        payload["source_pointer_path"] = str(Path(pointer_path).resolve())
        (temporary / "runtime_route_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "skhynix_official_ir_runtime_route_diagnostic_captured",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "source_count": len(evidence.source_summaries),
        "network_call_site_count": len(evidence.network_call_sites),
        "route_literal_count": len(evidence.route_literals),
        "attachment_context_count": len(evidence.attachment_contexts),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "source_pointer_path": str(Path(pointer_path).resolve()),
        "report_path": str((directory / "runtime_route_report.json").resolve()),
        "artifact_directory": str(directory.resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_runtime_route_diagnostic.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_RUNTIME_ROUTE_POINTER.name)
    return pointer


def load_runtime_route_diagnostic(
    pointer_path: str | Path = DEFAULT_RUNTIME_ROUTE_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrRuntimeRouteDiagnostic:
    pointer = _json_object(Path(pointer_path), "SK hynix runtime-route diagnostic pointer")
    if pointer.get("status") != "skhynix_official_ir_runtime_route_diagnostic_captured":
        raise ValueError("SK hynix runtime-route diagnostic pointer status is invalid")
    if pointer.get("discovery_only") is not True:
        raise ValueError("SK hynix runtime-route diagnostic must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix runtime-route diagnostic requires {flag}=false")
    source_pointer_path = Path(str(pointer.get("source_pointer_path", "")))
    reconstructed = build_runtime_route_diagnostic(
        source_pointer_path,
        evaluation_date=evaluation_date,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix runtime-route diagnostic does not reproduce from source bytes")
    if reconstructed.source_evidence_id != str(pointer.get("source_evidence_id", "")):
        raise ValueError("SK hynix runtime-route diagnostic source evidence mismatch")
    report = _json_object(
        Path(str(pointer.get("report_path", ""))),
        "SK hynix runtime-route diagnostic report",
    )
    if str(report.get("evidence_id", "")) != reconstructed.evidence_id:
        raise ValueError("SK hynix runtime-route diagnostic report evidence mismatch")
    expected = _diagnostic_payload(reconstructed)
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix runtime-route diagnostic report mismatch: {key}")
    return reconstructed


__all__ = [
    "DEFAULT_RUNTIME_ROUTE_OUTPUT",
    "DEFAULT_RUNTIME_ROUTE_POINTER",
    "OfficialIrRuntimeRouteDiagnostic",
    "RuntimeRouteSignal",
    "RuntimeSourceSummary",
    "build_runtime_route_diagnostic",
    "capture_runtime_route_diagnostic",
    "load_runtime_route_diagnostic",
    "scan_runtime_source",
]
