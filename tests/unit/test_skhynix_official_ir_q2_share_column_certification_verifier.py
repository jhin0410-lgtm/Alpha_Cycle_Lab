from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_share_column_certification as cert,
)
from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_share_column_certification_verifier as verifier,
)

OBSERVED_DATE = date(2026, 8, 15)


def _certification() -> cert.OfficialIrQ2ShareColumnCertification:
    columns = (
        cert.ShareColumnEvidence("'25 Q2", 448.4, ("77%", "21%"), 98.0),
        cert.ShareColumnEvidence("'26 Q1", 677.8, ("78%", "21%"), 99.0),
        cert.ShareColumnEvidence("'26 Q2", 908.6, ("73%", "27%"), 100.0),
    )
    provisional = {
        "geometry_evidence_id": "a" * 64,
        "source_certification_evidence_id": "b" * 64,
        "observed_date": OBSERVED_DATE.isoformat(),
        "source_url": "https://cdn.example.test/web/attach/q2.pdf",
        "pdf_sha256": "c" * 64,
        "page_number": 16,
        "quarter_labels": ["'25 Q2", "'26 Q1", "'26 Q2"],
        "columns": [cert._column_payload(value) for value in columns],
        "current_period_label": "'26 Q2",
        "current_period_start": "2026-04-01",
        "current_period_end": "2026-06-30",
        "current_column_percentage_tokens": ["73%", "27%"],
        "current_column_percentage_sum": 100.0,
        "product_legend_labels": ["DRAM", "NAND", "Others"],
        "footnote_verified": True,
        "period_column_semantics_certified": True,
        "product_assignment_certified": False,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return cert.OfficialIrQ2ShareColumnCertification(
        evidence_id=cert._sha_payload(provisional),
        geometry_evidence_id="a" * 64,
        source_certification_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256="c" * 64,
        page_number=16,
        quarter_labels=("'25 Q2", "'26 Q1", "'26 Q2"),
        columns=columns,
        current_period_label="'26 Q2",
        current_period_start="2026-04-01",
        current_period_end="2026-06-30",
        current_column_percentage_tokens=("73%", "27%"),
        current_column_percentage_sum=100.0,
        product_legend_labels=("DRAM", "NAND", "Others"),
        footnote_verified=True,
        period_column_semantics_certified=True,
    )


def _write_pointer(tmp_path: Path) -> Path:
    item = _certification()
    expected = cert._certification_payload(item)
    report_path = tmp_path / "share_column_certification.json"
    report_path.write_text(json.dumps(expected), encoding="utf-8")
    pointer = {
        **expected,
        "geometry_pointer_path": str(tmp_path / "geometry.json"),
        "report_path": str(report_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_verifier_rebuilds_share_column_certification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_pointer(tmp_path)
    item = _certification()
    monkeypatch.setattr(
        verifier,
        "load_q2_product_geometry",
        lambda pointer_path, *, evaluation_date: object(),
    )
    monkeypatch.setattr(
        cert,
        "build_q2_share_column_certification",
        lambda geometry_item: item,
    )

    loaded = verifier.load_q2_share_column_certification(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == item.evidence_id
    assert loaded.current_column_percentage_tokens == ("73%", "27%")
    assert loaded.product_assignment_certified is False


def test_verifier_rejects_product_assignment_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_pointer(tmp_path)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["product_assignment_certified"] = True
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "load_q2_product_geometry",
        lambda pointer_path, *, evaluation_date: object(),
    )

    with pytest.raises(ValueError, match="product_assignment_certified=false"):
        verifier.load_q2_share_column_certification(
            pointer_path,
            evaluation_date=OBSERVED_DATE,
        )
