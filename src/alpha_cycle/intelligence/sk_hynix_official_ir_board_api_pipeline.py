"""Production-facing orchestration for the verified SK hynix IR board API contract.

The issuer bundle exposes the board transport in two distinct layers:

* a shared board helper proves the literal ``GET /board/list`` route; and
* the Earnings Release component ``UI-FR-IR06`` proves bcode 105, page size 200, language
  selection, the ``실적발표=105`` category mapping, and ``cdnPath + fileUrl2`` PDF binding.

Those are separate source facts.  The first board-capture implementation required the
shared route to be attributed directly to ``UI-FR-IR06``.  The live archived bytes do not
make that attribution, so this orchestration deliberately validates the cross-component
contract without inventing a component identity.

All network and response parsing primitives remain in
``sk_hynix_official_ir_board_api_capture``.  This module only replaces the source-contract
validation/orchestration boundary and keeps every downstream eligibility flag false.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_board_api_capture as board_api
from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_component_contract_diagnostic import (
    DEFAULT_COMPONENT_CONTRACT_POINTER,
    OfficialIrComponentContractDiagnostic,
    load_component_contract_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_runtime_route_diagnostic import (
    _load_verified_archived_sources,
)

DEFAULT_BOARD_API_OUTPUT = board_api.DEFAULT_BOARD_API_OUTPUT
DEFAULT_BOARD_API_POINTER = board_api.DEFAULT_BOARD_API_POINTER
OfficialIrApiTransportContract = board_api.OfficialIrApiTransportContract
OfficialIrBoardApiCapture = board_api.OfficialIrBoardApiCapture

_COMPONENT_NAME = "UI-FR-IR06"
_EXPECTED_ROUTE = "/board/list"
_EXPECTED_BCODE = "105"
_EXPECTED_EARNINGS_MAPPING = "실적발표=105"
_EXPECTED_PAGE_SIZE_TOKEN = "pageSize=200"
_EXPECTED_LANG_TOKENS = ('?"KOR":"ENG"', '?"KOR":"ENG"')
_SHARED_BOARD_SOURCE_FILE = "script_03.js"
_NUXT_URL_ESCAPES = (
    (b"\\u002F", b"/"),
    (b"\\u002f", b"/"),
    (b"\\u003A", b":"),
    (b"\\u003a", b":"),
)


def _validate_shared_earnings_board_contract(
    component: OfficialIrComponentContractDiagnostic,
) -> None:
    """Validate the exact live shape without assigning a shared route to IR06."""

    shared_routes = {
        (item.source_file, item.method, item.value)
        for item in component.execute_routes
        if item.method == "get" and item.value == _EXPECTED_ROUTE
    }
    if (_SHARED_BOARD_SOURCE_FILE, "get", _EXPECTED_ROUTE) not in shared_routes:
        raise ValueError("SK hynix shared issuer board /board/list GET route is not verified")

    ir06_bcodes = {
        item.value
        for item in component.bcode_assignments
        if item.component_name == _COMPONENT_NAME
    }
    if ir06_bcodes != {_EXPECTED_BCODE}:
        raise ValueError("SK hynix Earnings Release bcode 105 contract is not uniquely verified")

    mappings = {item.value for item in component.earnings_code_mappings}
    if _EXPECTED_EARNINGS_MAPPING not in mappings:
        raise ValueError("SK hynix Earnings Release category mapping 실적발표=105 is not verified")

    ir06_set_board = [
        item
        for item in component.method_windows
        if item.component_name == _COMPONENT_NAME and item.value == "setBoard"
    ]
    if len(ir06_set_board) != 1:
        raise ValueError("SK hynix Earnings Release setBoard contract is not uniquely verified")
    set_board_context = ir06_set_board[0].context.replace(" ", "")
    if _EXPECTED_PAGE_SIZE_TOKEN not in set_board_context:
        raise ValueError("SK hynix Earnings Release pageSize=200 contract is not verified")
    if not all(token in set_board_context for token in ("KOR", "ENG", "lang")):
        raise ValueError("SK hynix Earnings Release KOR/ENG language contract is not verified")

    earnings_pdf_bindings = [
        item
        for item in component.file_url_bindings
        if item.source_file == _SHARED_BOARD_SOURCE_FILE
        and item.value.endswith("fileUrl2")
    ]
    if not earnings_pdf_bindings:
        raise ValueError("SK hynix Earnings Release fileUrl2 download binding is not verified")


def _normalize_transport_source_bytes(data: bytes) -> bytes:
    """Decode only URL-structural JSON escapes used in archived Nuxt config literals."""

    normalized = data.replace(b"\\/", b"/")
    for encoded, decoded in _NUXT_URL_ESCAPES:
        normalized = normalized.replace(encoded, decoded)
    return normalized


def build_api_transport_contract(
    source_pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    component_pointer_path: str | Path = DEFAULT_COMPONENT_CONTRACT_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrApiTransportContract:
    """Build the transport contract from the live shared-board source shape."""

    component = load_component_contract_diagnostic(
        component_pointer_path,
        evaluation_date=evaluation_date,
    )
    _validate_shared_earnings_board_contract(component)

    source_evidence_id, observed_date, sources = _load_verified_archived_sources(
        source_pointer_path,
        evaluation_date=evaluation_date,
    )
    if source_evidence_id != component.source_evidence_id:
        raise ValueError("SK hynix board contract and archived source evidence IDs differ")

    page_rows = [row for row in sources if row[0] == "official_ir_page.html"]
    if len(page_rows) != 1:
        raise ValueError("SK hynix API transport requires exactly one archived official page")
    page_origin = board_api._origin(page_rows[0][1])

    signals: list[board_api.ApiBaseSignal] = []
    config_contexts: list[str] = []
    get_contexts: list[str] = []
    for source_file, source_url, data in sources:
        source_signals, source_configs, source_gets = board_api.scan_api_transport_source(
            source_file=source_file,
            source_url=source_url,
            page_origin=page_origin,
            data=_normalize_transport_source_bytes(data),
        )
        signals.extend(source_signals)
        config_contexts.extend(source_configs)
        get_contexts.extend(source_gets)

    resolved_api_base, resolution_status = board_api._resolve_api_base(tuple(signals))
    payload = {
        "source_evidence_id": source_evidence_id,
        "component_evidence_id": component.evidence_id,
        "observed_date": observed_date.isoformat(),
        "page_origin": page_origin,
        "base_signals": [board_api._signal_payload(item) for item in signals],
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
        evidence_id=board_api._sha_payload(payload),
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


def capture_official_ir_board_api(
    source_pointer_path: str | Path = DEFAULT_DISCOVERY_POINTER,
    component_pointer_path: str | Path = DEFAULT_COMPONENT_CONTRACT_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_BOARD_API_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Capture the board response only after the corrected transport contract resolves."""

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
            json.dumps(
                board_api._transport_payload(transport),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        raise ValueError(
            "SK hynix API base is not uniquely resolved from archived issuer bytes; "
            f"transport diagnostic written to {diagnostic_path}"
        )

    request_url, params, response_bytes = board_api.download_board_api_response(
        transport,
        timeout_seconds=timeout_seconds,
    )
    capture = board_api.build_board_api_capture(
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
            json.dumps(
                board_api._transport_payload(transport),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (temporary / "board_list_response.json").write_bytes(response_bytes)
        (temporary / "board_list_capture.json").write_text(
            json.dumps(
                board_api._capture_payload(capture),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 2,
        "status": "skhynix_official_ir_board_api_captured",
        "contract_shape": "shared_board_route_plus_ir06_parameters",
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
    """Rebuild the v2 shared-board capture from verified source and response bytes."""

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
    if pointer.get("contract_shape") != "shared_board_route_plus_ir06_parameters":
        raise ValueError("SK hynix board API pointer contract shape is invalid")
    if pointer.get("discovery_only") is not True:
        raise ValueError("SK hynix board API pointer must remain discovery-only")
    for flag in board_api._REQUIRED_FALSE_FLAGS:
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
    response_sha = hashlib.sha256(response_bytes).hexdigest()
    if response_sha != str(pointer.get("response_sha256", "")):
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

    reconstructed = board_api.build_board_api_capture(
        transport,
        response_bytes=response_bytes,
        request_url=str(report.get("request_url", "")),
        request_params=tuple(params),
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix board API capture does not reproduce from archived bytes")
    expected = board_api._capture_payload(reconstructed)
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix board API capture report mismatch: {key}")
    return reconstructed


__all__ = [
    "DEFAULT_BOARD_API_OUTPUT",
    "DEFAULT_BOARD_API_POINTER",
    "OfficialIrApiTransportContract",
    "OfficialIrBoardApiCapture",
    "build_api_transport_contract",
    "capture_official_ir_board_api",
    "load_board_api_capture",
]
