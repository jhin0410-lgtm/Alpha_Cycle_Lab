"""Trace exact SK hynix IR component contracts from archived issuer JavaScript.

This second-stage diagnostic consumes only the already verified official-IR discovery
artifact. It extracts syntactically constrained component contracts that can justify a
later network-capture step without guessing an endpoint or attachment identifier.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_runtime_route_diagnostic import (
    _load_verified_archived_sources,
)

DEFAULT_COMPONENT_CONTRACT_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-component-contract-diagnostic"
)
DEFAULT_COMPONENT_CONTRACT_POINTER = (
    DEFAULT_COMPONENT_CONTRACT_OUTPUT
    / "latest_skhynix_ir_component_contract_diagnostic.json"
)

_CONTEXT_CHARS = 900
_COMPONENT_LOOKBACK = 12_000
_MAX_METHOD_WINDOWS = 24
_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)

_COMPONENT_NAME = re.compile(r"\bname\s*:\s*([\"'])(?P<name>[^\"']{1,100})\1")
_EXECUTE_LITERAL_ROUTE = re.compile(
    r"(?P<helper>[A-Za-z_$][\w$]*)\.execute\.(?P<method>get|post)\(\s*"
    r"(?P<context_arg>this|[A-Za-z_$][\w$]*)\s*,\s*"
    r"(?P<quote>[\"'])(?P<route>/[^\"']{1,180})(?P=quote)",
    flags=re.IGNORECASE,
)
_BCODE_ASSIGNMENT = re.compile(
    r"(?:this\.)?board\.parameter\.bcode\s*=\s*(?P<value>\d{1,4})",
    flags=re.IGNORECASE,
)
_EARNINGS_CODE_MAPPING = re.compile(
    r"(?P<quote>[\"'])(?P<label>실적발표|Earnings(?:\s+Release|\s+Results)?)"
    r"(?P=quote)\s*:\s*(?P<value>\d{1,4})",
    flags=re.IGNORECASE,
)
_CDN_PATH_LITERAL = re.compile(
    r"\bcdnPath\s*:\s*(?P<quote>[\"'])(?P<url>https://[^\"']{1,300})"
    r"(?P=quote)",
    flags=re.IGNORECASE,
)
_FILE_URL_BINDING = re.compile(
    r"(?P<base>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.cdnPath\s*\+\s*"
    r"(?P<field>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.fileUrl[1-4])",
    flags=re.IGNORECASE,
)
_QUERY_METHOD = re.compile(
    r"\b(?P<method>queryBoardList|setBoard|queryBoardView)\s*:\s*function\s*\(",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ComponentContractSignal:
    source_file: str
    source_url: str
    component_name: str | None
    kind: str
    value: str
    method: str | None
    context: str


@dataclass(frozen=True)
class OfficialIrComponentContractDiagnostic:
    evidence_id: str
    source_evidence_id: str
    observed_date: date
    execute_routes: tuple[ComponentContractSignal, ...]
    bcode_assignments: tuple[ComponentContractSignal, ...]
    earnings_code_mappings: tuple[ComponentContractSignal, ...]
    cdn_paths: tuple[ComponentContractSignal, ...]
    file_url_bindings: tuple[ComponentContractSignal, ...]
    method_windows: tuple[ComponentContractSignal, ...]
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.source_evidence_id):
            raise ValueError("SK hynix component-contract IDs must be SHA-256")
        if not self.discovery_only:
            raise ValueError("SK hynix component-contract diagnostic must be discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix component-contract diagnostic cannot widen trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\\/", "/")


def _compact(value: str) -> str:
    return " ".join(value.split())


def _context(text: str, start: int, end: int) -> str:
    half = _CONTEXT_CHARS // 2
    left = max(0, start - half)
    right = min(len(text), end + half)
    return _compact(text[left:right])[:_CONTEXT_CHARS]


def _nearest_component_name(text: str, position: int) -> str | None:
    left = max(0, position - _COMPONENT_LOOKBACK)
    nearest: str | None = None
    for match in _COMPONENT_NAME.finditer(text, left, position):
        nearest = match.group("name")
    return nearest


def _signal(
    *,
    source_file: str,
    source_url: str,
    text: str,
    match: re.Match[str],
    kind: str,
    value: str,
    method: str | None = None,
    extra_context: int = 0,
) -> ComponentContractSignal:
    return ComponentContractSignal(
        source_file=source_file,
        source_url=source_url,
        component_name=_nearest_component_name(text, match.start()),
        kind=kind,
        value=value,
        method=method,
        context=_context(text, match.start(), min(len(text), match.end() + extra_context)),
    )


def _signal_payload(item: ComponentContractSignal) -> dict[str, object]:
    return {
        "source_file": item.source_file,
        "source_url": item.source_url,
        "component_name": item.component_name,
        "kind": item.kind,
        "value": item.value,
        "method": item.method,
        "context": item.context,
    }


def scan_component_contracts(
    *,
    source_file: str,
    source_url: str,
    data: bytes,
) -> tuple[
    tuple[ComponentContractSignal, ...],
    tuple[ComponentContractSignal, ...],
    tuple[ComponentContractSignal, ...],
    tuple[ComponentContractSignal, ...],
    tuple[ComponentContractSignal, ...],
    tuple[ComponentContractSignal, ...],
]:
    """Extract exact component-contract shapes from one archived source."""

    text = _normalized_text(data)
    execute_routes = tuple(
        _signal(
            source_file=source_file,
            source_url=source_url,
            text=text,
            match=match,
            kind="execute_literal_route",
            value=match.group("route"),
            method=match.group("method").lower(),
        )
        for match in _EXECUTE_LITERAL_ROUTE.finditer(text)
    )
    bcode_assignments = tuple(
        _signal(
            source_file=source_file,
            source_url=source_url,
            text=text,
            match=match,
            kind="board_bcode_assignment",
            value=match.group("value"),
        )
        for match in _BCODE_ASSIGNMENT.finditer(text)
    )
    earnings_code_mappings = tuple(
        _signal(
            source_file=source_file,
            source_url=source_url,
            text=text,
            match=match,
            kind="earnings_code_mapping",
            value=f"{match.group('label')}={match.group('value')}",
        )
        for match in _EARNINGS_CODE_MAPPING.finditer(text)
    )
    cdn_paths = tuple(
        _signal(
            source_file=source_file,
            source_url=source_url,
            text=text,
            match=match,
            kind="cdn_path_literal",
            value=match.group("url"),
        )
        for match in _CDN_PATH_LITERAL.finditer(text)
    )
    file_url_bindings = tuple(
        _signal(
            source_file=source_file,
            source_url=source_url,
            text=text,
            match=match,
            kind="file_url_binding",
            value=f"{match.group('base')}.cdnPath+{match.group('field')}",
        )
        for match in _FILE_URL_BINDING.finditer(text)
    )

    method_windows: list[ComponentContractSignal] = []
    for match in _QUERY_METHOD.finditer(text):
        if len(method_windows) >= _MAX_METHOD_WINDOWS:
            break
        method_windows.append(
            _signal(
                source_file=source_file,
                source_url=source_url,
                text=text,
                match=match,
                kind="component_method_window",
                value=match.group("method"),
                method=match.group("method"),
                extra_context=360,
            )
        )
    return (
        execute_routes,
        bcode_assignments,
        earnings_code_mappings,
        cdn_paths,
        file_url_bindings,
        tuple(method_windows),
    )


def build_component_contract_diagnostic(
    pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrComponentContractDiagnostic:
    source_evidence_id, observed_date, sources = _load_verified_archived_sources(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    groups: list[list[ComponentContractSignal]] = [[] for _ in range(6)]
    for source_file, source_url, data in sources:
        extracted = scan_component_contracts(
            source_file=source_file,
            source_url=source_url,
            data=data,
        )
        for index, items in enumerate(extracted):
            groups[index].extend(items)

    execute_routes = tuple(groups[0])
    bcode_assignments = tuple(groups[1])
    earnings_code_mappings = tuple(groups[2])
    cdn_paths = tuple(groups[3])
    file_url_bindings = tuple(groups[4])
    method_windows = tuple(groups[5])
    payload = {
        "source_evidence_id": source_evidence_id,
        "observed_date": observed_date.isoformat(),
        "execute_routes": [_signal_payload(item) for item in execute_routes],
        "bcode_assignments": [_signal_payload(item) for item in bcode_assignments],
        "earnings_code_mappings": [
            _signal_payload(item) for item in earnings_code_mappings
        ],
        "cdn_paths": [_signal_payload(item) for item in cdn_paths],
        "file_url_bindings": [_signal_payload(item) for item in file_url_bindings],
        "method_windows": [_signal_payload(item) for item in method_windows],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrComponentContractDiagnostic(
        evidence_id=_sha_payload(payload),
        source_evidence_id=source_evidence_id,
        observed_date=observed_date,
        execute_routes=execute_routes,
        bcode_assignments=bcode_assignments,
        earnings_code_mappings=earnings_code_mappings,
        cdn_paths=cdn_paths,
        file_url_bindings=file_url_bindings,
        method_windows=method_windows,
    )


def _evidence_payload(
    evidence: OfficialIrComponentContractDiagnostic,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_component_contract_diagnostic_captured",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "execute_route_count": len(evidence.execute_routes),
        "bcode_assignment_count": len(evidence.bcode_assignments),
        "earnings_code_mapping_count": len(evidence.earnings_code_mappings),
        "cdn_path_count": len(evidence.cdn_paths),
        "file_url_binding_count": len(evidence.file_url_bindings),
        "method_window_count": len(evidence.method_windows),
        "execute_routes": [_signal_payload(item) for item in evidence.execute_routes],
        "bcode_assignments": [_signal_payload(item) for item in evidence.bcode_assignments],
        "earnings_code_mappings": [
            _signal_payload(item) for item in evidence.earnings_code_mappings
        ],
        "cdn_paths": [_signal_payload(item) for item in evidence.cdn_paths],
        "file_url_bindings": [
            _signal_payload(item) for item in evidence.file_url_bindings
        ],
        "method_windows": [_signal_payload(item) for item in evidence.method_windows],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def capture_component_contract_diagnostic(
    pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_COMPONENT_CONTRACT_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence = build_component_contract_diagnostic(
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
        raise ValueError("SK hynix component-contract artifact path already exists")
    temporary.mkdir()
    try:
        report = _evidence_payload(evidence)
        report["captured_at"] = captured.isoformat()
        report["source_pointer_path"] = str(Path(pointer_path).resolve())
        report_path = temporary / "component_contract_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    final_report_path = directory / "component_contract_report.json"
    pointer = {
        "schema_version": 1,
        "status": "skhynix_official_ir_component_contract_diagnostic_captured",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "execute_route_count": len(evidence.execute_routes),
        "bcode_assignment_count": len(evidence.bcode_assignments),
        "earnings_code_mapping_count": len(evidence.earnings_code_mappings),
        "cdn_path_count": len(evidence.cdn_paths),
        "file_url_binding_count": len(evidence.file_url_bindings),
        "method_window_count": len(evidence.method_windows),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "source_pointer_path": str(Path(pointer_path).resolve()),
        "report_path": str(final_report_path.resolve()),
        "artifact_directory": str(directory.resolve()),
    }
    pointer_tmp = root / ".latest_skhynix_ir_component_contract_diagnostic.json.tmp"
    pointer_tmp.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pointer_tmp.replace(root / DEFAULT_COMPONENT_CONTRACT_POINTER.name)
    return pointer


def _json_mapping(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): value for key, value in raw.items()}


def load_component_contract_diagnostic(
    pointer_path: str | Path = DEFAULT_COMPONENT_CONTRACT_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrComponentContractDiagnostic:
    pointer = _json_mapping(
        Path(pointer_path),
        "SK hynix component-contract diagnostic pointer",
    )
    expected_status = "skhynix_official_ir_component_contract_diagnostic_captured"
    if pointer.get("status") != expected_status:
        raise ValueError("SK hynix component-contract pointer status is invalid")
    if pointer.get("discovery_only") is not True:
        raise ValueError("SK hynix component-contract diagnostic must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix component-contract diagnostic requires {flag}=false")

    reconstructed = build_component_contract_diagnostic(
        Path(str(pointer.get("source_pointer_path", ""))),
        evaluation_date=evaluation_date,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError(
            "SK hynix component-contract diagnostic does not reproduce from source bytes"
        )
    report = _json_mapping(
        Path(str(pointer.get("report_path", ""))),
        "SK hynix component-contract diagnostic report",
    )
    for key, value in _evidence_payload(reconstructed).items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix component-contract report mismatch: {key}")
    return reconstructed


__all__ = [
    "ComponentContractSignal",
    "DEFAULT_COMPONENT_CONTRACT_OUTPUT",
    "DEFAULT_COMPONENT_CONTRACT_POINTER",
    "OfficialIrComponentContractDiagnostic",
    "build_component_contract_diagnostic",
    "capture_component_contract_diagnostic",
    "load_component_contract_diagnostic",
    "scan_component_contracts",
]
