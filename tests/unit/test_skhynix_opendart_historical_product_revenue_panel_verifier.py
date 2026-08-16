from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    HistoricalProductRevenuePanelEntry,
    build_historical_product_revenue_panel_evidence,
    historical_period_id,
    load_historical_product_revenue_specs,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)


def _failed(period: str, document_id: str) -> HistoricalProductRevenuePanelEntry:
    return HistoricalProductRevenuePanelEntry(
        period_id=period,
        document_id=document_id,
        status="failed",
        pointer_path=None,
        certification_evidence_id=None,
        chain_evidence_id=None,
        rcept_no=None,
        error_type="ValueError",
    )


def _write_panel_pointer(tmp_path, entries):
    evidence = build_historical_product_revenue_panel_evidence(
        evaluation_date=date(2026, 8, 16),
        entries=entries,
    )
    panel_path = tmp_path / "panel.json"
    panel_path.write_text(json.dumps({"evidence_id": evidence.evidence_id}), encoding="utf-8")
    pointer = {
        **asdict(evidence),
        "evaluation_date": "2026-08-16",
        "entries": [asdict(item) for item in evidence.entries],
        "schema_version": 1,
        "status": "skhynix_opendart_historical_product_revenue_panel_captured",
        "panel_path": str(panel_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path, evidence


def test_verifier_accepts_complete_all_failed_diagnostic_panel(tmp_path) -> None:
    specs = load_historical_product_revenue_specs()
    entries = tuple(
        _failed(historical_period_id(spec), spec.document_id)
        for spec in specs
    )
    pointer_path, expected = _write_panel_pointer(tmp_path, entries)
    verified = load_historical_product_revenue_panel_evidence(
        pointer_path,
        evaluation_date=date(2026, 8, 16),
    )
    assert verified.evidence_id == expected.evidence_id
    assert verified.successful_periods == ()
    assert len(verified.failed_periods) == 10
    assert verified.full_source_coverage_certified is False


def test_verifier_replays_each_certified_period_chain(monkeypatch, tmp_path) -> None:
    specs = load_historical_product_revenue_specs()
    certified_spec = specs[0]
    period = historical_period_id(certified_spec)
    period_pointer = tmp_path / "period_pointer.json"
    period_pointer.write_text(json.dumps({"chain_evidence_id": "b" * 64}), encoding="utf-8")
    certified = HistoricalProductRevenuePanelEntry(
        period_id=period,
        document_id=certified_spec.document_id,
        status="certified",
        pointer_path=str(period_pointer),
        certification_evidence_id="a" * 64,
        chain_evidence_id="b" * 64,
        rcept_no="20230515000001",
        error_type=None,
    )
    entries = (certified,) + tuple(
        _failed(historical_period_id(spec), spec.document_id)
        for spec in specs[1:]
    )
    pointer_path, expected = _write_panel_pointer(tmp_path, entries)

    import alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier as panel_verifier

    monkeypatch.setattr(
        panel_verifier,
        "load_periodic_product_revenue_certification",
        lambda *args, **kwargs: SimpleNamespace(
            evidence_id="a" * 64,
            rcept_no="20230515000001",
        ),
    )
    verified = load_historical_product_revenue_panel_evidence(
        pointer_path,
        evaluation_date=date(2026, 8, 16),
    )
    assert verified.evidence_id == expected.evidence_id
    assert verified.successful_periods == ("2023Q1",)
    assert len(verified.failed_periods) == 9
