from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_runtime_route_diagnostic as diagnostic
from alpha_cycle.intelligence.sk_hynix_official_ir_runtime_route_diagnostic import (
    DEFAULT_RUNTIME_ROUTE_POINTER,
    build_runtime_route_diagnostic,
    capture_runtime_route_diagnostic,
    load_runtime_route_diagnostic,
    scan_runtime_source,
)

SOURCE_EVIDENCE_ID = "a" * 64
OBSERVED_DATE = date(2026, 8, 15)


def test_scan_runtime_source_finds_literal_routes_and_network_calls() -> None:
    data = b"""
    const route = "/api/ir/earnings/list";
    const attachmentBase = "/web/attach/";
    fetch(route, {method: "POST"});
    axios.get("/api/ir/file/download?id=" + fileId);
    function downloadFile(fileId) { return fileId; }
    """
    summary, network, routes, contexts = scan_runtime_source(
        source_file="script_01.js",
        source_url="https://www.skhynix.com/assets/ir.js",
        data=data,
    )

    assert summary.network_call_site_count >= 2
    assert {item.token for item in network} >= {"fetch", "axios"}
    literals = {item.literal for item in routes}
    assert "/api/ir/earnings/list" in literals
    assert "/web/attach/" in literals
    assert "/api/ir/file/download?id=" in literals
    assert any(item.token == "download" for item in contexts)


def test_scan_runtime_source_never_synthesizes_endpoint_from_identifier_only() -> None:
    data = b"const attachmentId = payload.fileId; const name = 'attachmentId';"
    summary, network, routes, contexts = scan_runtime_source(
        source_file="script_02.js",
        source_url="https://www.skhynix.com/assets/common.js",
        data=data,
    )

    assert summary.network_call_site_count == 0
    assert network == ()
    assert routes == ()
    assert contexts
    assert all(item.literal is None for item in contexts)


def _fake_sources() -> tuple[str, date, tuple[tuple[str, str, bytes], ...]]:
    return (
        SOURCE_EVIDENCE_ID,
        OBSERVED_DATE,
        (
            (
                "official_ir_page.html",
                "https://www.skhynix.com/ir/UI-FR-IR06/",
                b'<script src="/assets/ir.js"></script>',
            ),
            (
                "script_01.js",
                "https://www.skhynix.com/assets/ir.js",
                b'fetch("/api/ir/earnings/list"); const x="/web/attach/";',
            ),
        ),
    )


def test_build_runtime_route_diagnostic_is_source_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostic,
        "_load_verified_archived_sources",
        lambda pointer_path, evaluation_date: _fake_sources(),
    )
    evidence = build_runtime_route_diagnostic(
        "ignored.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert evidence.source_evidence_id == SOURCE_EVIDENCE_ID
    assert evidence.observed_date == OBSERVED_DATE
    assert len(evidence.source_summaries) == 2
    assert any(item.literal == "/api/ir/earnings/list" for item in evidence.route_literals)
    assert evidence.discovery_only is True
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_capture_and_load_reproduce_report_and_reject_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostic,
        "_load_verified_archived_sources",
        lambda pointer_path, evaluation_date: _fake_sources(),
    )
    pointer = capture_runtime_route_diagnostic(
        "ignored.json",
        evaluation_date=OBSERVED_DATE,
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 18, 0, tzinfo=UTC),
    )
    pointer_path = tmp_path / DEFAULT_RUNTIME_ROUTE_POINTER.name
    loaded = load_runtime_route_diagnostic(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == pointer["evidence_id"]

    report_path = Path(str(pointer["report_path"]))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["route_literal_count"] = 999
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="report mismatch"):
        load_runtime_route_diagnostic(
            pointer_path,
            evaluation_date=OBSERVED_DATE,
        )
