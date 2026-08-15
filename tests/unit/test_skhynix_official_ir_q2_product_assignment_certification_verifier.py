from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_assignment_certification as assignment
from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_product_assignment_certification_verifier as verifier,
)

OBSERVED_DATE = date(2026, 8, 15)


def _certification() -> assignment.OfficialIrQ2ProductAssignmentCertification:
    gray = assignment.FillStyle("gray", (0.749,))
    red = assignment.FillStyle("rgb", (0.89, 0.098, 0.216))
    orange = assignment.FillStyle("rgb", (0.961, 0.502, 0.145))
    dram_swatch = assignment.PaintedRectangle(265.2, 199.68, 9.96, -9.96, orange)
    nand_swatch = assignment.PaintedRectangle(265.2, 241.92, 9.96, -9.96, red)
    other_swatch = assignment.PaintedRectangle(265.2, 284.28, 9.96, -9.96, gray)
    dram_segment = assignment.PaintedRectangle(879.96, 841.92, 114.84, -663.72, orange)
    nand_segment = assignment.PaintedRectangle(879.96, 1083.48, 114.84, -241.56, red)
    other_segment = assignment.PaintedRectangle(879.96, 1088.52, 114.84, -5.04, gray)
    return assignment.OfficialIrQ2ProductAssignmentCertification(
        evidence_id="a" * 64,
        share_column_evidence_id="b" * 64,
        geometry_evidence_id="c" * 64,
        source_certification_evidence_id="d" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256="e" * 64,
        page_number=16,
        current_period_label="'26 Q2",
        legend_bindings=(
            assignment.LegendBinding("DRAM", 279.708, 189.207, dram_swatch),
            assignment.LegendBinding("NAND", 279.708, 231.502, nand_swatch),
            assignment.LegendBinding("Others", 279.708, 273.796, other_swatch),
        ),
        product_share_bindings=(
            assignment.ProductShareBinding(
                "DRAM",
                "73%",
                73.0,
                908.635,
                520.396,
                dram_segment,
            ),
            assignment.ProductShareBinding(
                "NAND",
                "27%",
                27.0,
                908.675,
                959.313,
                nand_segment,
            ),
        ),
        others_segment=other_segment,
        dram_share_percent=73.0,
        nand_share_percent=27.0,
        other_share_percent=None,
        product_assignment_certified=True,
        dram_nand_share_semantics_certified=True,
        others_segment_present=True,
    )


def _write_pointer(tmp_path: Path) -> tuple[Path, Path]:
    item = _certification()
    expected = assignment._certification_payload(item)
    report_path = tmp_path / "product_assignment_certification.json"
    report_path.write_text(json.dumps(expected), encoding="utf-8")
    geometry_pointer = tmp_path / "geometry.json"
    pointer = {
        **expected,
        "share_column_pointer_path": str(tmp_path / "share.json"),
        "geometry_pointer_path": str(geometry_pointer),
        "report_path": str(report_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path, geometry_pointer


def test_verifier_rebuilds_product_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path, geometry_pointer = _write_pointer(tmp_path)
    item = _certification()
    monkeypatch.setattr(
        assignment,
        "_load_inputs_from_share_pointer",
        lambda share_pointer, *, evaluation_date: (
            object(),
            object(),
            b"%PDF-fixture",
            geometry_pointer,
        ),
    )
    monkeypatch.setattr(
        assignment,
        "build_q2_product_assignment_certification",
        lambda share_item, geometry_item, *, pdf_bytes: item,
    )

    loaded = verifier.load_q2_product_assignment_certification(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.dram_share_percent == 73.0
    assert loaded.nand_share_percent == 27.0
    assert loaded.other_share_percent is None
    assert loaded.other_zero_certified is False


def test_verifier_rejects_other_zero_promotion(tmp_path: Path) -> None:
    pointer_path, _ = _write_pointer(tmp_path)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["other_zero_certified"] = True
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="other_zero_certified=false"):
        verifier.load_q2_product_assignment_certification(
            pointer_path,
            evaluation_date=OBSERVED_DATE,
        )
