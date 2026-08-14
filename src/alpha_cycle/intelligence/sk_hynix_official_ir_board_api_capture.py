"""Resolve and capture the SK hynix Earnings Release board API without guessing transport.

The official issuer JavaScript already proves the component contract for the Earnings
Release page: bcode 105, a literal ``/board/list`` GET route, and download bindings built
from ``cdnPath + fileUrlN``.  What it does not prove by itself is the effective browser
Axios base URL.  This module therefore separates two trust steps:

1. Rebuild an API transport contract only from the already archived, verified issuer page
   and JavaScript bytes.  A base URL is resolved only from an explicit literal
   ``browserBaseURL``/``browserBaseUrl``/``baseURL``/``baseUrl`` assignment.  Generic
   framework fallbacks, localhost defaults, page origins, and sibling routes are never
   promoted by inference.
2. Only when that transport contract resolves uniquely, issue the exact read-only
   ``/board/list`` request encoded by the verified UI-FR-IR06 component and archive the
   raw JSON bytes.  The response remains discovery-only until a later source-specific
   document registry/parser contract certifies the returned attachment.

No result from this module can directly activate a product baseline, allocation resolver,
forecast, valuation, score, order, or trade path.
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
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_component_contract_diagnostic import (
    DEFAULT_COMPONENT_CONTRACT_POINTER,
    load_component_contract_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_runtime_route_diagnostic import (
    _load_verified_archived_sources,
)

DEFAULT_BOARD_API_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-board-api-capture"
)
DEFAULT_BOARD_API_POINTER = DEFAULT_BOARD_API_OUTPUT / "latest_skhynix_ir_board_api_capture.json"

_COMPONENT_NAME = "UI-FR-IR06"
_EXPECTED_ROUTE = "/board/list"
_EXPECTED_BCODE = 105
_EXPECTED_PAGE = 1
_EXPECTED_PAGE_SIZE = 200
_EXPECTED_LANG = "ENG"
_ALLOWED_BASE_KEYS = ("browserBaseURL", "browserBaseUrl", "baseURL", "baseUrl")
_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)
_BASE_LITERAL = re.compile(
    r"(?P<key>browserBaseURL|browserBaseUrl|baseURL|baseUrl)\s*[:=]\s*"
    r"(?P<quote>[\"'])(?P<value>https?://[^\"']{1,300}|/[^\"']{0,180})(?P=quote)",
    flags=re.IGNORECASE,
)
_AXIOS_CONFIG_CONTEXT = re.compile(
    r"(?:\$config\s*&&\s*[^;]{0,240}\baxios\b|\baxios\s*:\s*\{)",
    flags=re.IGNORECASE,
)
_AXIOS_GET = re.compile(r"\$axios\.get\s*\(", flags=re.IGNORECASE)


@dataclass(frozen=True)
class ApiBaseSignal:
    source_file: str
    source_url: str
    key: str
    raw_value: str
    resolved_value: str
    context: str


@dataclass(frozen=True)
class OfficialIrApiTransportContract:
    evidence_id: str
    source_evidence_id: str
    component_evidence_id: str
    observed_date: date
    page_origin: str
    base_signals: tuple[ApiBaseSignal, ...]
    axios_config_contexts: tuple[str, ...]
    axios_get_contexts: tuple[str, ...]
    resolved_api_base: str | None
    resolution_status: str
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("SK hynix API transport evidence ID must be SHA-256")
        if not _valid_sha(self.source_evidence_id) or not _valid_sha(self.component_evidence_id):
            raise ValueError("SK hynix API transport source IDs must be SHA-256")
        if self.resolution_status not in {"resolved", "unresolved_no_literal", "unresolved_ambiguous"}:
            raise ValueError("SK hynix API transport resolution status is invalid")
        if (self.resolved_api_base is None) == (self.resolution_status == "resolved"):
            raise ValueError("SK hynix API transport resolution fields are inconsistent")
        if not self.discovery_only:
            raise ValueError("SK hynix API transport contract must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix API transport contract cannot widen model trust")


@dataclass(frozen=True)
class BoardRowSummary:
    seq: str
    title: str
    display_date: str
    file_url1: str | None
    file_url2: str | None
    file_url3: str | None
    file_url4: str | None
    candidate_2026q2: bool


@dataclass(frozen=True)
class OfficialIrBoardApiCapture:
    evidence_id: str
    transport_evidence_id: str
    observed_date: date
    request_url: str
    request_params: tuple[tuple[str, str], ...]
    response_sha256: str
    cdn_url: str
    total: int
    rows: tuple[BoardRowSummary, ...]
    candidate_seqs: tuple[str, ...]
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.transport_evidence_id):
            raise ValueError("SK hynix board API evidence IDs must be SHA-256")
        if not _valid_sha(self.response_sha256):
            raise ValueError("SK hynix board API response hash must be SHA-256")
        if not self.request_url.startswith("https://"):
            raise ValueError("SK hynix board API request must use HTTPS")
        if self.total < len(self.rows):
            raise ValueError("SK hynix board API total cannot be smaller than returned rows")
        if not self.discovery_only:
            raise ValueError("SK hynix board API capture must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix board API capture cannot widen model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _compact(value: str) -> str:
    return " ".join(value.split())


def _context(text: str, start: int, end: int, *, width: int = 520) -> str:
    half = width // 2
    return _compact(text[max(0, start - half) : min(len(text), end + half)])[:width]


def _signal_payload(item: ApiBaseSignal) -> dict[str, object]:
    return {
        "source_file": item.source_file,
        "source_url": item.source_url,
        "key": item.key,
        "raw_value": item.raw_value,
        "resolved_value": item.resolved_value,
        "context": item.context,
    }


def _row_payload(item: BoardRowSummary) -> dict[str, object]:
    return {
        "seq": item.seq,
        "title": item.title,
        "display_date": item.display_date,
        "file_url1": item.file_url1,
        "file_url2": item.file_url2,
        "file_url3": item.file_url3,
        "file_url4": item.file_url4,
        "candidate_2026q2": item.candidate_2026q2,
    }


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("SK hynix official page origin must be HTTPS")
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"https://{parsed.hostname}{port}"


def _resolve_base_literal(page_origin: str, value: str) -> str | None:
    if value.startswith("/"):
        return urljoin(page_origin + "/", value)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return None
    return value.rstrip("/")


def scan_api_transport_source(
    *,
    source_file: str,
    source_url: str,
    page_origin: str,
    data: bytes,
) -> tuple[tuple[ApiBaseSignal, ...], tuple[str, ...], tuple[str, ...]]:
    """Extract explicit Axios base assignments and bounded helper contexts."""

    text = data.decode("utf-8", errors="replace").replace("\\/", "/")
    base_signals: list[ApiBaseSignal] = []
    seen: set[tuple[str, str]] = set()
    for match in _BASE_LITERAL.finditer(text):
        key = match.group("key")
        raw = match.group("value")
        resolved = _resolve_base_literal(page_origin, raw)
        if resolved is None or (key.casefold(), resolved) in seen:
            continue
        seen.add((key.casefold(), resolved))
        base_signals.append(
            ApiBaseSignal(
                source_file=source_file,
                source_url=source_url,
                key=key,
                raw_value=raw,
                resolved_value=resolved,
                context=_context(text, match.start(), match.end()),
            )
        )

    config_contexts = tuple(
        _context(text, match.start(), match.end(), width=760)
        for match in list(_AXIOS_CONFIG_CONTEXT.finditer(text))[:12]
    )
    get_contexts = tuple(
        _context(text, match.start(), match.end(), width=760)
        for match in list(_AXIOS_GET.finditer(text))[:12]
    )
    return tuple(base_signals), config_contexts, get_contexts


def _resolve_api_base(signals: tuple[ApiBaseSignal, ...]) -> tuple[str | None, str]:
    browser = {
        item.resolved_value
        for item in signals
        if item.key.casefold() in {"browserbaseurl"}
    }
    if len(browser) == 1:
        return next(iter(browser)), "resolved"
    if len(browser) > 1:
        return None, "unresolved_ambiguous"

    generic = {
        item.resolved_value
        for item in signals
        if item.key.casefold() == "baseurl"
    }
    if len(generic) == 1:
        return next(iter(generic)), "resolved"
    if len(generic) > 1:
        return None, "unresolved_ambiguous"
    return None, "unresolved_no_literal"


def build_api_transport_contract(
    source_pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    component_pointer_path: str | Path = DEFAULT_COMPONENT_CONTRACT_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrApiTransportContract:
    component = load_component_contract_diagnostic(
        component_pointer_path,
        evaluation_date=evaluation_date,
    )
    component_routes = {
        (item.component_name, item.method, item.value) for item in component.execute_routes
    }
    if (_COMPONENT_NAME, "get", _EXPECTED_ROUTE) not in component_routes:
        raise ValueError("SK hynix Earnings Release /board/list component contract is not verified")
    component_bcodes = {
        int(item.value)
        for item in component.bcode_assignments
        if item.component_name == _COMPONENT_NAME
    }
    if component_bcodes != {_EXPECTED_BCODE}:
        raise ValueError("SK hynix Earnings Release bcode 105 contract is not uniquely verified")
    if not any(
        item.value.endswith("fileUrl2") for item in component.file_url_bindings
    ):
        raise ValueError("SK hynix Earnings Release fileUrl2 download binding is not verified")

    source_evidence_id, observed_date, sources = _load_verified_archived_sources(
        source_pointer_path,
        evaluation_date=evaluation_date,
    )
    page_rows = [row for row in sources if row[0] == "official_ir_page.html"]
    if len(page_rows) != 1:
        raise ValueError("SK hynix API transport requires exactly one archived official page")
    page_origin = _origin(page_rows[0][1])

    signals: list[ApiBaseSignal] = []
    config_contexts: list[str] = []
    get_contexts: list[str] = []
    for source_file, source_url, data in sources:
        source_signals, source_configs, source_gets = scan_api_transport_source(
            source_file=source_file,
            source_url=source_url,
            page_origin=page_origin,
            data=data,
        )
        signals.extend(source_signals)
        config_contexts.extend(source_configs)
        get_contexts.extend(source_gets)

    resolved_api_base, resolution_status = _resolve_api_base(tuple(signals))
    payload = {
        "source_evidence_id": source_evidence_id,
        "component_evidence_id": component.evidence_id,
        "observed_date": observed_date.isoformat(),
        "page_origin": page_origin,
        "base_signals": [_signal_payload(item) for item in signals],
        "axios_config_contexts": config_contexts,
        "axios_get_contexts": get_contexts,
        "resolved_api_base": resolved_api_base,
        "resolution_status": resolution_status,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrApiTransportContract(
        evidence_id=_sha_payload(payload),
        source_evidence_id=source_evidence_id,
        component_evidence_id=component.evidence_id,
        observed_date=observed_date,
        page_origin=page_origin,
        base_signals=tuple(signals),
        axios_config_contexts=tuple(config_contexts),
        axios_get_contexts=tuple(get_contexts),
        resolved_api_base=resolved_api_base,
        resolution_status=resolution_status,
    )


def _nullable_string(row: dict[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_2026q2_candidate(title: str, display_date: str) -> bool:
    folded = title.casefold().replace(" ", "")
    period_signal = any(token in folded for token in ("2q26", "2q2026", "2026q2", "2분기"))
    year_signal = "2026" in folded or display_date.startswith("2026")
    return period_signal and year_signal


def parse_board_api_response(data: bytes) -> tuple[str, int, tuple[BoardRowSummary, ...]]:
    try:
        payload: object = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix board API response is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("SK hynix board API response must be a JSON object")
    raw = cast(dict[object, object], payload)
    cdn_url = str(raw.get("cdnUrl", "")).strip()
    if not cdn_url.startswith("https://"):
        raise ValueError("SK hynix board API response is missing HTTPS cdnUrl")
    rows_raw = raw.get("list")
    if not isinstance(rows_raw, list):
        raise ValueError("SK hynix board API response list is missing")
    try:
        total = int(str(raw.get("total", "")))
    except ValueError as exc:
        raise ValueError("SK hynix board API response total is invalid") from exc

    rows: list[BoardRowSummary] = []
    for index, item in enumerate(rows_raw):
        if not isinstance(item, dict):
            raise ValueError(f"SK hynix board API row {index} is not an object")
        row = {str(key): value for key, value in cast(dict[object, object], item).items()}
        seq = str(row.get("seq", "")).strip()
        title = str(row.get("title", "")).strip()
        display_date = str(row.get("displayDate", "")).strip()
        if not seq or not title or not display_date:
            raise ValueError(f"SK hynix board API row {index} lacks seq/title/displayDate")
        rows.append(
            BoardRowSummary(
                seq=seq,
                title=title,
                display_date=display_date,
                file_url1=_nullable_string(row, "fileUrl1"),
                file_url2=_nullable_string(row, "fileUrl2"),
                file_url3=_nullable_string(row, "fileUrl3"),
                file_url4=_nullable_string(row, "fileUrl4"),
                candidate_2026q2=_is_2026q2_candidate(title, display_date),
            )
        )
    if total < len(rows):
        raise ValueError("SK hynix board API total is smaller than returned list")
    return cdn_url.rstrip("/"), total, tuple(rows)


def _request_params() -> tuple[tuple[str, str], ...]:
    return (
        ("bcode", str(_EXPECTED_BCODE)),
        ("lang", _EXPECTED_LANG),
        ("page", str(_EXPECTED_PAGE)),
        ("pageSize", str(_EXPECTED_PAGE_SIZE)),
    )


def download_board_api_response(
    transport: OfficialIrApiTransportContract,
    *,
    timeout_seconds: float = 20.0,
) -> tuple[str, tuple[tuple[str, str], ...], bytes]:
    if transport.resolution_status != "resolved" or transport.resolved_api_base is None:
        raise ValueError(
            "SK hynix board API transport is unresolved; refusing to guess an API base URL"
        )
    request_url = transport.resolved_api_base.rstrip("/") + _EXPECTED_ROUTE
    if not request_url.startswith("https://"):
        raise ValueError("SK hynix board API resolved request is not HTTPS")
    params = _request_params()
    request = Request(
        request_url + "?" + urlencode(params),
        headers={
            "Accept": "application/json",
            "User-Agent": "Alpha-Cycle-Lab/0.1 skhynix-ir-readonly",
            "Referer": "https://www.skhynix.com/ir/UI-FR-IR06/",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        content = bytes(response.read())
    return request_url, params, content


def build_board_api_capture(
    transport: OfficialIrApiTransportContract,
    *,
    response_bytes: bytes,
    request_url: str,
    request_params: tuple[tuple[str, str], ...],
) -> OfficialIrBoardApiCapture:
    expected_url = (transport.resolved_api_base or "").rstrip("/") + _EXPECTED_ROUTE
    if transport.resolution_status != "resolved" or request_url != expected_url:
        raise ValueError("SK hynix board API request URL does not match resolved transport")
    if request_params != _request_params():
        raise ValueError("SK hynix board API request parameters changed from UI-FR-IR06 contract")
    cdn_url, total, rows = parse_board_api_response(response_bytes)
    response_sha = hashlib.sha256(response_bytes).hexdigest()
    candidate_seqs = tuple(item.seq for item in rows if item.candidate_2026q2)
    payload = {
        "transport_evidence_id": transport.evidence_id,
        "observed_date": transport.observed_date.isoformat(),
        "request_url": request_url,
        "request_params": list(request_params),
        "response_sha256": response_sha,
        "cdn_url": cdn_url,
        "total": total,
        "rows": [_row_payload(item) for item in rows],
        "candidate_seqs": list(candidate_seqs),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrBoardApiCapture(
        evidence_id=_sha_payload(payload),
        transport_evidence_id=transport.evidence_id,
        observed_date=transport.observed_date,
        request_url=request_url,
        request_params=request_params,
        response_sha256=response_sha,
        cdn_url=cdn_url,
        total=total,
        rows=rows,
        candidate_seqs=candidate_seqs,
    )


def _transport_payload(contract: OfficialIrApiTransportContract) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_api_transport_contract",
        "evidence_id": contract.evidence_id,
        "source_evidence_id": contract.source_evidence_id,
        "component_evidence_id": contract.component_evidence_id,
        "observed_date": contract.observed_date.isoformat(),
        "page_origin": contract.page_origin,
        "base_signals": [_signal_payload(item) for item in contract.base_signals],
        "axios_config_contexts": list(contract.axios_config_contexts),
        "axios_get_contexts": list(contract.axios_get_contexts),
        "resolved_api_base": contract.resolved_api_base,
        "resolution_status": contract.resolution_status,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _capture_payload(capture: OfficialIrBoardApiCapture) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_board_api_captured",
        "evidence_id": capture.evidence_id,
        "transport_evidence_id": capture.transport_evidence_id,
        "observed_date": capture.observed_date.isoformat(),
        "request_url": capture.request_url,
        "request_params": [list(item) for item in capture.request_params],
        "response_sha256": capture.response_sha256,
        "cdn_url": capture.cdn_url,
        "total": capture.total,
        "row_count": len(capture.rows),
        "candidate_seqs": list(capture.candidate_seqs),
        "rows": [_row_payload(item) for item in capture.rows],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def capture_official_ir_board_api(
    source_pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    component_pointer_path: str | Path = DEFAULT_COMPONENT_CONTRACT_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_BOARD_API_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    transport = build_api_transport_contract(
        source_pointer_path,
        component_pointer_path,
        evaluation_date=evaluation_date,
    )
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    if transport.resolution_status != "resolved":
        diagnostic_path = root / "latest_skhynix_ir_api_transport_contract.json"
        diagnostic_path.write_text(
            json.dumps(_transport_payload(transport), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        raise ValueError(
            "SK hynix API base is not uniquely resolved from archived issuer bytes; "
            f"transport diagnostic written to {diagnostic_path}"
        )

    request_url, params, response_bytes = download_board_api_response(
        transport,
        timeout_seconds=timeout_seconds,
    )
    capture = build_board_api_capture(
        transport,
        response_bytes=response_bytes,
        request_url=request_url,
        request_params=params,
    )
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + capture.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix board API artifact path already exists")
    temporary.mkdir()
    try:
        (temporary / "transport_contract.json").write_text(
            json.dumps(_transport_payload(transport), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "board_list_response.json").write_bytes(response_bytes)
        (temporary / "board_list_capture.json").write_text(
            json.dumps(_capture_payload(capture), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "skhynix_official_ir_board_api_captured",
        "evidence_id": capture.evidence_id,
        "transport_evidence_id": transport.evidence_id,
        "source_evidence_id": transport.source_evidence_id,
        "component_evidence_id": transport.component_evidence_id,
        "observed_date": transport.observed_date.isoformat(),
        "request_url": capture.request_url,
        "response_sha256": capture.response_sha256,
        "cdn_url": capture.cdn_url,
        "row_count": len(capture.rows),
        "candidate_seqs": list(capture.candidate_seqs),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "source_pointer_path": str(Path(source_pointer_path).resolve()),
        "component_pointer_path": str(Path(component_pointer_path).resolve()),
        "artifact_directory": str(directory.resolve()),
        "response_path": str((directory / "board_list_response.json").resolve()),
        "capture_path": str((directory / "board_list_capture.json").resolve()),
        "transport_path": str((directory / "transport_contract.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_board_api_capture.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_BOARD_API_POINTER.name)
    return pointer


def load_board_api_capture(
    pointer_path: str | Path = DEFAULT_BOARD_API_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrBoardApiCapture:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix board API pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix board API pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_board_api_captured":
        raise ValueError("SK hynix board API pointer status is invalid")
    if pointer.get("discovery_only") is not True:
        raise ValueError("SK hynix board API pointer must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix board API pointer requires {flag}=false")

    transport = build_api_transport_contract(
        Path(str(pointer.get("source_pointer_path", ""))),
        Path(str(pointer.get("component_pointer_path", ""))),
        evaluation_date=evaluation_date,
    )
    if transport.evidence_id != str(pointer.get("transport_evidence_id", "")):
        raise ValueError("SK hynix board API transport evidence no longer reproduces")
    response_path = Path(str(pointer.get("response_path", "")))
    response_bytes = response_path.read_bytes()
    if hashlib.sha256(response_bytes).hexdigest() != str(pointer.get("response_sha256", "")):
        raise ValueError("SK hynix board API archived response hash mismatch")
    capture_path = Path(str(pointer.get("capture_path", "")))
    try:
        capture_obj: object = json.loads(capture_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix board API capture report is unreadable") from exc
    if not isinstance(capture_obj, dict):
        raise ValueError("SK hynix board API capture report must be an object")
    report = {str(key): value for key, value in capture_obj.items()}
    raw_params = report.get("request_params")
    if not isinstance(raw_params, list):
        raise ValueError("SK hynix board API request parameters are invalid")
    params: list[tuple[str, str]] = []
    for item in raw_params:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("SK hynix board API request parameter row is invalid")
        params.append((str(item[0]), str(item[1])))
    reconstructed = build_board_api_capture(
        transport,
        response_bytes=response_bytes,
        request_url=str(report.get("request_url", "")),
        request_params=tuple(params),
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix board API capture does not reproduce from archived bytes")
    expected = _capture_payload(reconstructed)
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix board API capture report mismatch: {key}")
    return reconstructed


__all__ = [
    "ApiBaseSignal",
    "BoardRowSummary",
    "DEFAULT_BOARD_API_OUTPUT",
    "DEFAULT_BOARD_API_POINTER",
    "OfficialIrApiTransportContract",
    "OfficialIrBoardApiCapture",
    "build_api_transport_contract",
    "build_board_api_capture",
    "capture_official_ir_board_api",
    "download_board_api_response",
    "load_board_api_capture",
    "parse_board_api_response",
    "scan_api_transport_source",
]
