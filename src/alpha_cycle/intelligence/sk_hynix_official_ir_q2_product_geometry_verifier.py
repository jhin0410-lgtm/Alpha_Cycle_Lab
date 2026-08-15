"""Rebuild SK hynix 2Q26 product geometry from archived official PDF bytes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_source_certification_verifier import (
    load_q2_source_certification,
)


def load_q2_product_geometry(
    pointer_path: str | Path = geometry.DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER,
    *,
    evaluation_date: date,
) -> geometry.OfficialIrQ2ProductGeometry:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 product-geometry pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 product-geometry pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_product_geometry_captured":
        raise ValueError("SK hynix Q2 product-geometry pointer status is invalid")
    for flag in geometry._REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 product geometry requires {flag}=false")

    certification_pointer = Path(
        str(pointer.get("source_certification_pointer_path", ""))
    )
    certification = load_q2_source_certification(
        certification_pointer,
        evaluation_date=evaluation_date,
    )
    pdf_bytes = geometry._load_pdf_bytes_from_certification_pointer(certification_pointer)
    reconstructed = geometry.build_q2_product_geometry(
        certification,
        pdf_bytes=pdf_bytes,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 product geometry no longer reproduces")

    expected = geometry._geometry_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"SK hynix Q2 product-geometry pointer mismatch: {key}")

    report_path = Path(str(pointer.get("report_path", "")))
    try:
        report_obj: object = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 product-geometry report is unreadable") from exc
    if report_obj != expected:
        raise ValueError("SK hynix Q2 product-geometry report payload mismatch")
    return reconstructed


__all__ = ["load_q2_product_geometry"]
