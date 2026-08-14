from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_board_api_capture as capture
from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_capture import (
    ApiBaseSignal,
    OfficialIrApiTransportContract,
    build_api_transport_contract,
    build_board_api_capture,
    download_board_api_response,
    parse_board_api_response,
    scan_api_transport_source,
)

OBSERVED_DATE = date(2026, 8, 15)
SOURCE_ID = "a" * 64
COMPONENT_ID = "b" * 64


def _component_contract() -> SimpleNamespace:
    return SimpleNamespace(
        evidence_id=COMPONENT_ID,
        execute_routes=(
            SimpleNamespace(
                component_name="UI-FR-IR06",
                method="get",
                value="/board/list",
            ),
        ),
        bcode_assignments=(
            SimpleNamespace(component_name="UI-FR-IR06", value="105"),
        ),
        file_url_bindings=(
            SimpleNamespace(value="t.board.cdnPath+t.lastOne.fileUrl2"),
        ),
    )


def _patch_verified_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    script_bytes: bytes,
) -> None:
    monkeypatch.setattr(
        capture,
        "load_component_contract_diagnostic",
        lambda pointer_path, *, evaluation_date: _component_contract(),
    )
    monkeypatch.setattr(
        capture,
        "_load_verified_archived_sources",
        lambda pointer_path, *, evaluation_date: (
            SOURCE_ID,
            OBSERVED_DATE,
            (
                (
                    "official_ir_page.html",
                    "https://www.skhynix.com/ir/UI-FR-IR06/",
                    b"<html></html>",
                ),
                (
                    "script.js",
                    "https://www.skhynix.com/_nuxt/script.js",
                    script_bytes,
                ),
            ),
        ),
    )


def _resolved_transport() -> OfficialIrApiTransportContract:
    signal = ApiBaseSignal(
        source_file="script.js",
        source_url="https://www.skhynix.com/_nuxt/script.js",
        key="browserBaseURL",
        raw_value="https://api.example.test",
        resolved_value="https://api.example.test",
        context="browserBaseURL:'https://api.example.test'",
    )
    provisional = {
        "source_evidence_id": SOURCE_ID,
        "component_evidence_id": COMPONENT_ID,
        "observed_date": OBSERVED_DATE.isoformat(),
        "page_origin": "https://www.skhynix.com",
        "base_signals": [capture._signal_payload(signal)],
        "axios_config_contexts": [],
        "axios_get_contexts": [],
        "resolved_api_base": "https://api.example.test",
        "resolution_status": "resolved",
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrApiTransportContract(
        evidence_id=capture._sha_payload(provisional),
        source_evidence_id=SOURCE_ID,
        component_evidence_id=COMPONENT_ID,
        observed_date=OBSERVED_DATE,
        page_origin="https://www.skhynix.com",
        base_signals=(signal,),
        axios_config_contexts=(),
        axios_get_contexts=(),
        resolved_api_base="https://api.example.test",
        resolution_status="resolved",
    )


def _board_response() -> bytes:
    return json.dumps(
        {
            "cdnUrl": "https://cdn.example.test/web",
            "total": 2,
            "list": [
                {
                    "seq": 9001,
                    "title": "2026년 2분기 실적발표",
                    "displayDate": "2026.07.29",
                    "fileUrl1": "/call.mp3",
                    "fileUrl2": "/2026q2_earnings.pdf",
                    "fileUrl3": "/2026q2_press.pdf",
                    "fileUrl4": "/2026q2_ceo.pdf",
                },
                {
                    "seq": 8001,
                    "title": "2026년 1분기 실적발표",
                    "displayDate": "2026.04.24",
                    "fileUrl2": "/2026q1_earnings.pdf",
                },
            ],
        },
        ensure_ascii=False,
    ).encode()


def test_scan_api_transport_source_accepts_only_explicit_base_assignment() -> None:
    signals, configs, gets = scan_api_transport_source(
        source_file="script.js",
        source_url="https://www.skhynix.com/_nuxt/script.js",
        page_origin="https://www.skhynix.com",
        data=(
            b'var cfg={axios:{browserBaseURL:"https://api.example.test"}};'
            b't.$axios.get(n);'
        ),
    )

    assert [(item.key, item.resolved_value) for item in signals] == [
        ("browserBaseURL", "https://api.example.test")
    ]
    assert configs
    assert gets


def test_framework_fallback_and_page_origin_do_not_resolve_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified_sources(
        monkeypatch,
        script_bytes=(
            b'var n=t.$config&&t.$config.axios||{},r=n.browserBaseURL||n.baseURL||'
            b'"http://localhost:3000";t.$axios.get(n);'
        ),
    )
    contract = build_api_transport_contract(
        "source.json",
        "component.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert contract.resolution_status == "unresolved_no_literal"
    assert contract.resolved_api_base is None
    assert contract.page_origin == "https://www.skhynix.com"


def test_unique_browser_base_resolves_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_sources(
        monkeypatch,
        script_bytes=(
            b'window.__NUXT__={config:{axios:{browserBaseURL:"https://api.example.test"}}};'
            b't.$axios.get(n);'
        ),
    )
    contract = build_api_transport_contract(
        "source.json",
        "component.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert contract.resolution_status == "resolved"
    assert contract.resolved_api_base == "https://api.example.test"
    assert contract.product_baseline_eligible is False
    assert contract.allocation_resolver_registered is False


def test_ambiguous_browser_bases_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verified_sources(
        monkeypatch,
        script_bytes=(
            b'browserBaseURL:"https://api-a.example.test";'
            b'browserBaseURL:"https://api-b.example.test";'
        ),
    )
    contract = build_api_transport_contract(
        "source.json",
        "component.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert contract.resolution_status == "unresolved_ambiguous"
    assert contract.resolved_api_base is None


def test_parse_board_api_response_preserves_returned_attachment_fields() -> None:
    cdn_url, total, rows = parse_board_api_response(_board_response())

    assert cdn_url == "https://cdn.example.test/web"
    assert total == 2
    assert rows[0].seq == "9001"
    assert rows[0].file_url2 == "/2026q2_earnings.pdf"
    assert rows[0].candidate_2026q2 is True
    assert rows[1].candidate_2026q2 is False


def test_board_capture_uses_exact_verified_request_contract() -> None:
    transport = _resolved_transport()
    params = (
        ("bcode", "105"),
        ("lang", "ENG"),
        ("page", "1"),
        ("pageSize", "200"),
    )
    result = build_board_api_capture(
        transport,
        response_bytes=_board_response(),
        request_url="https://api.example.test/board/list",
        request_params=params,
    )

    assert result.candidate_seqs == ("9001",)
    assert result.response_sha256 == capture.hashlib.sha256(_board_response()).hexdigest()
    assert result.discovery_only is True
    assert result.product_baseline_eligible is False


def test_changed_request_parameters_are_rejected() -> None:
    with pytest.raises(ValueError, match="request parameters changed"):
        build_board_api_capture(
            _resolved_transport(),
            response_bytes=_board_response(),
            request_url="https://api.example.test/board/list",
            request_params=(("bcode", "105"), ("page", "2")),
        )


def test_unresolved_transport_never_sends_network_request() -> None:
    unresolved = OfficialIrApiTransportContract(
        evidence_id="c" * 64,
        source_evidence_id=SOURCE_ID,
        component_evidence_id=COMPONENT_ID,
        observed_date=OBSERVED_DATE,
        page_origin="https://www.skhynix.com",
        base_signals=(),
        axios_config_contexts=(),
        axios_get_contexts=(),
        resolved_api_base=None,
        resolution_status="unresolved_no_literal",
    )
    with pytest.raises(ValueError, match="refusing to guess"):
        download_board_api_response(unresolved)


def test_invalid_board_response_schema_fails_closed() -> None:
    with pytest.raises(ValueError, match="cdnUrl"):
        parse_board_api_response(b'{"total":1,"list":[]}')
