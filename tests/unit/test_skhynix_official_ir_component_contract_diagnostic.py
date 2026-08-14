from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence import (
    sk_hynix_official_ir_component_contract_diagnostic as diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_component_contract_diagnostic import (
    DEFAULT_COMPONENT_CONTRACT_POINTER,
    build_component_contract_diagnostic,
    capture_component_contract_diagnostic,
    load_component_contract_diagnostic,
    scan_component_contracts,
)

SOURCE_EVIDENCE_ID = "a" * 64
OBSERVED_DATE = date(2026, 8, 15)
SOURCE_URL = "https://www.skhynix.com/_nuxt/component.js"

COMPONENT_BYTES = (
    'name:"IR-EARNINGS",data:function(){return{board:{'
    'cdnPath:"https://issuer.example/web"}}},methods:{'
    'setBoard:function(){this.board.parameter.bcode=105;'
    'this.board.parameter.pageSize=100},queryBoardList:function(){'
    'var t=this;r.execute.get(this,"/performance/list",this.board.parameter,'
    'function(e){t.board.list=e.list;t.lastOne=e.list[0]})},'
    'queryBoardView:function(){r.execute.get(this,"/performance/detail",'
    '{seq:this.seq},function(e){return e})}},render:function(){return '
    't.board.cdnPath+t.lastOne.fileUrl2+t.board.cdnPath+line.fileUrl3};'
    'var code={"실적발표":105};'
).encode()


def _patch_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        diagnostic,
        "_load_verified_archived_sources",
        lambda pointer_path, *, evaluation_date: (
            SOURCE_EVIDENCE_ID,
            OBSERVED_DATE,
            (("script_03.js", SOURCE_URL, COMPONENT_BYTES),),
        ),
    )


def test_scan_component_contracts_extracts_exact_routes_and_file_bindings() -> None:
    execute, bcodes, mappings, cdns, bindings, windows = scan_component_contracts(
        source_file="script_03.js",
        source_url=SOURCE_URL,
        data=COMPONENT_BYTES,
    )

    assert {(item.method, item.value) for item in execute} == {
        ("get", "/performance/list"),
        ("get", "/performance/detail"),
    }
    assert {item.value for item in bcodes} == {"105"}
    assert {item.value for item in mappings} == {"실적발표=105"}
    assert {item.value for item in cdns} == {"https://issuer.example/web"}
    assert {item.value for item in bindings} == {
        "t.board.cdnPath+t.lastOne.fileUrl2",
        "t.board.cdnPath+line.fileUrl3",
    }
    assert {item.value for item in windows} >= {
        "setBoard",
        "queryBoardList",
        "queryBoardView",
    }
    assert all(item.component_name == "IR-EARNINGS" for item in execute)


def test_identifier_only_text_never_becomes_execute_route() -> None:
    data = (
        b'name:"IR",methods:{queryBoardList:function(){'
        b"var attachmentId=row.attachmentId;"
        b'var routeName="/performance/list";return routeName}}'
    )
    execute, bcodes, mappings, cdns, bindings, windows = scan_component_contracts(
        source_file="script.js",
        source_url=SOURCE_URL,
        data=data,
    )

    assert execute == ()
    assert bcodes == ()
    assert mappings == ()
    assert cdns == ()
    assert bindings == ()
    assert {item.value for item in windows} == {"queryBoardList"}


def test_build_component_contract_diagnostic_is_discovery_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sources(monkeypatch)
    evidence = build_component_contract_diagnostic(
        "ignored.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert evidence.source_evidence_id == SOURCE_EVIDENCE_ID
    assert [item.value for item in evidence.execute_routes] == [
        "/performance/list",
        "/performance/detail",
    ]
    assert evidence.discovery_only is True
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_capture_and_load_rebuilds_from_source_and_rejects_report_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_sources(monkeypatch)
    pointer = capture_component_contract_diagnostic(
        "ignored.json",
        evaluation_date=OBSERVED_DATE,
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 18, 0, tzinfo=UTC),
    )
    pointer_path = tmp_path / DEFAULT_COMPONENT_CONTRACT_POINTER.name
    loaded = load_component_contract_diagnostic(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == pointer["evidence_id"]

    report_path = Path(str(pointer["report_path"]))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["execute_route_count"] = 999
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="report mismatch"):
        load_component_contract_diagnostic(
            pointer_path,
            evaluation_date=OBSERVED_DATE,
        )
