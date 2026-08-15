from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_board_api_pipeline as pipeline

OBSERVED_DATE = date(2026, 8, 15)
SOURCE_EVIDENCE_ID = "a" * 64
COMPONENT_EVIDENCE_ID = "b" * 64


def _signal(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _live_component_contract(
    *,
    include_mapping: bool = True,
    page_size: str = "200",
) -> SimpleNamespace:
    mappings = ((_signal(value="실적발표=105"),) if include_mapping else ())
    return SimpleNamespace(
        evidence_id=COMPONENT_EVIDENCE_ID,
        source_evidence_id=SOURCE_EVIDENCE_ID,
        execute_routes=(
            _signal(
                source_file="script_03.js",
                component_name="COMP-UI-FR-IR12-T2",
                method="get",
                value="/board/list",
            ),
            _signal(
                source_file="script_03.js",
                component_name="UI-FR-IR06",
                method="get",
                value="/performance/detail",
            ),
        ),
        bcode_assignments=(
            _signal(component_name="COMP-UI-FR-IR12-T2", value="103"),
            _signal(component_name="UI-FR-IR06", value="105"),
        ),
        earnings_code_mappings=mappings,
        file_url_bindings=(
            _signal(
                source_file="script_03.js",
                component_name="show",
                value="t.board.cdnPath+t.lastOne.fileUrl2",
            ),
        ),
        method_windows=(
            _signal(
                component_name="UI-FR-IR06",
                value="setBoard",
                context=(
                    "setBoard:function(){this.board.parameter.bcode=105;"
                    f"this.board.parameter.pageSize={page_size};"
                    'this.board.parameter.lang=this.langk()?"KOR":"ENG"}'
                ),
            ),
        ),
    )


def _patch_live_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    component: SimpleNamespace | None = None,
    script_bytes: bytes = b'browserBaseURL:"https://api.example.test"',
) -> None:
    monkeypatch.setattr(
        pipeline,
        "load_component_contract_diagnostic",
        lambda pointer_path, *, evaluation_date: component or _live_component_contract(),
    )
    monkeypatch.setattr(
        pipeline,
        "_load_verified_archived_sources",
        lambda pointer_path, *, evaluation_date: (
            SOURCE_EVIDENCE_ID,
            OBSERVED_DATE,
            (
                (
                    "official_ir_page.html",
                    "https://www.skhynix.com/ir/UI-FR-IR06/",
                    b"<html></html>",
                ),
                (
                    "script_02.js",
                    "https://www.skhynix.com/_nuxt/runtime.js",
                    script_bytes,
                ),
            ),
        ),
    )


def test_live_shared_route_shape_builds_transport_without_false_component_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_live_sources(monkeypatch)

    contract = pipeline.build_api_transport_contract(
        "source.json",
        "component.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert contract.resolution_status == "resolved"
    assert contract.resolved_api_base == "https://api.example.test"
    assert contract.source_evidence_id == SOURCE_EVIDENCE_ID
    assert contract.component_evidence_id == COMPONENT_EVIDENCE_ID
    assert contract.product_baseline_eligible is False
    assert contract.allocation_resolver_registered is False


def test_live_nuxt_unicode_escaped_baseurl_resolves_from_archived_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_live_sources(
        monkeypatch,
        script_bytes=(
            b'window.__NUXT__={config:{axios:{baseURL:"https:\\u002F\\u002F'
            b'homeapi.skhynix.com"}}};'
        ),
    )

    contract = pipeline.build_api_transport_contract(
        "source.json",
        "component.json",
        evaluation_date=OBSERVED_DATE,
    )

    assert contract.resolution_status == "resolved"
    assert contract.resolved_api_base == "https://homeapi.skhynix.com"
    assert [(item.key, item.resolved_value) for item in contract.base_signals] == [
        ("baseURL", "https://homeapi.skhynix.com")
    ]
    assert contract.product_baseline_eligible is False
    assert contract.allocation_resolver_registered is False
    assert contract.numeric_forecast_enabled is False
    assert contract.decision_score_enabled is False


def test_nuxt_url_normalization_does_not_promote_localhost_fallback() -> None:
    normalized = pipeline._normalize_transport_source_bytes(
        b'baseURL:"http:\\u002F\\u002Flocalhost:3000"'
    )
    signals, _, _ = pipeline.board_api.scan_api_transport_source(
        source_file="official_ir_page.html",
        source_url="https://www.skhynix.com/ir/UI-FR-IR06/",
        page_origin="https://www.skhynix.com",
        data=normalized,
    )

    assert signals == ()


def test_shared_route_may_not_be_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    component = _live_component_contract()
    component.execute_routes = tuple(
        item for item in component.execute_routes if item.value != "/board/list"
    )
    _patch_live_sources(monkeypatch, component=component)

    with pytest.raises(ValueError, match="shared issuer board /board/list"):
        pipeline.build_api_transport_contract(
            "source.json",
            "component.json",
            evaluation_date=OBSERVED_DATE,
        )


def test_earnings_mapping_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_live_sources(
        monkeypatch,
        component=_live_component_contract(include_mapping=False),
    )

    with pytest.raises(ValueError, match="category mapping"):
        pipeline.build_api_transport_contract(
            "source.json",
            "component.json",
            evaluation_date=OBSERVED_DATE,
        )


def test_ir06_page_size_200_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_live_sources(
        monkeypatch,
        component=_live_component_contract(page_size="100"),
    )

    with pytest.raises(ValueError, match="pageSize=200"):
        pipeline.build_api_transport_contract(
            "source.json",
            "component.json",
            evaluation_date=OBSERVED_DATE,
        )


def test_source_and_component_evidence_must_share_same_archived_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_live_sources(monkeypatch)
    monkeypatch.setattr(
        pipeline,
        "_load_verified_archived_sources",
        lambda pointer_path, *, evaluation_date: (
            "c" * 64,
            OBSERVED_DATE,
            (
                (
                    "official_ir_page.html",
                    "https://www.skhynix.com/ir/UI-FR-IR06/",
                    b"<html></html>",
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="evidence IDs differ"):
        pipeline.build_api_transport_contract(
            "source.json",
            "component.json",
            evaluation_date=OBSERVED_DATE,
        )
