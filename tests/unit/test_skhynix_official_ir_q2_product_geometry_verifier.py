from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_product_geometry_verifier as verifier,
)

OBSERVED_DATE = date(2026, 8, 15)


def _geometry() -> geometry.OfficialIrQ2ProductGeometry:
    fragment = geometry.TextFragment(
        page_number=16,
        text="DRAM",
        text_matrix=(1.0, 0.0, 0.0, 1.0, 100.0, 300.0),
        current_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_size=10.0,
    )
    page = geometry.ProductGeometryPage(
        page_number=16,
        width=612.0,
        height=792.0,
        fragments=(fragment,),
        focus_fragments=(fragment,),
    )
    provisional = {
        "source_certification_evidence_id": "a" * 64,
        "observed_date": OBSERVED_DATE.isoformat(),
        "source_url": "https://cdn.example.test/web/attach/q2.pdf",
        "pdf_sha256": "b" * 64,
        "pages": [geometry._page_payload(page)],
        "readiness_status": "geometry_ready_for_semantic_review",
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return geometry.OfficialIrQ2ProductGeometry(
        evidence_id=geometry._sha_payload(provisional),
        source_certification_evidence_id="a" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256="b" * 64,
        pages=(page,),
        readiness_status="geometry_ready_for_semantic_review",
    )


def _write_pointer(tmp_path: Path) -> Path:
    item = _geometry()
    expected = geometry._geometry_payload(item)
    report_path = tmp_path / "product_geometry.json"
    report_path.write_text(json.dumps(expected), encoding="utf-8")
    pointer = {
        **expected,
        "source_certification_pointer_path": str(tmp_path / "certification.json"),
        "report_path": str(report_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_verifier_rebuilds_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_pointer(tmp_path)
    item = _geometry()
    monkeypatch.setattr(
        verifier,
        "load_q2_source_certification",
        lambda pointer_path, *, evaluation_date: object(),
    )
    monkeypatch.setattr(
        geometry,
        "_load_pdf_bytes_from_certification_pointer",
        lambda pointer_path: b"pdf",
    )
    monkeypatch.setattr(
        geometry,
        "build_q2_product_geometry",
        lambda certification, *, pdf_bytes: item,
    )

    loaded = verifier.load_q2_product_geometry(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == item.evidence_id


def test_verifier_rejects_persisted_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_pointer(tmp_path)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["readiness_status"] = "geometry_missing"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    item = _geometry()
    monkeypatch.setattr(
        verifier,
        "load_q2_source_certification",
        lambda pointer_path, *, evaluation_date: object(),
    )
    monkeypatch.setattr(
        geometry,
        "_load_pdf_bytes_from_certification_pointer",
        lambda pointer_path: b"pdf",
    )
    monkeypatch.setattr(
        geometry,
        "build_q2_product_geometry",
        lambda certification, *, pdf_bytes: item,
    )

    with pytest.raises(ValueError, match="pointer mismatch"):
        verifier.load_q2_product_geometry(pointer_path, evaluation_date=OBSERVED_DATE)
