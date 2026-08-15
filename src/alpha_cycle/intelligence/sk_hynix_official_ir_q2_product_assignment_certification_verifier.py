"""Rebuild SK hynix 2Q26 product-assignment evidence from archived issuer bytes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_assignment_certification as assignment


def load_q2_product_assignment_certification(
    pointer_path: str | Path = assignment.DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER,
    *,
    evaluation_date: date,
) -> assignment.OfficialIrQ2ProductAssignmentCertification:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 product-assignment pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 product-assignment pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_product_assignment_certified":
        raise ValueError("SK hynix Q2 product-assignment pointer status is invalid")
    if pointer.get("product_assignment_certified") is not True:
        raise ValueError("SK hynix Q2 product assignment must remain certified")
    if pointer.get("dram_nand_share_semantics_certified") is not True:
        raise ValueError("SK hynix Q2 DRAM/NAND share semantics must remain certified")
    if pointer.get("others_segment_present") is not True:
        raise ValueError("SK hynix Q2 Others display segment must remain present")
    if pointer.get("other_share_percent") is not None:
        raise ValueError("SK hynix Q2 Other share must remain numerically unresolved")
    for flag in assignment._REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 product assignment requires {flag}=false")

    share_pointer = Path(str(pointer.get("share_column_pointer_path", "")))
    share_item, geometry_item, pdf_bytes, geometry_pointer = (
        assignment._load_inputs_from_share_pointer(
            share_pointer,
            evaluation_date=evaluation_date,
        )
    )
    if str(geometry_pointer.resolve()) != str(
        Path(str(pointer.get("geometry_pointer_path", ""))).resolve()
    ):
        raise ValueError("SK hynix Q2 product-assignment geometry pointer diverged")

    reconstructed = assignment.build_q2_product_assignment_certification(
        share_item,
        geometry_item,
        pdf_bytes=pdf_bytes,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 product assignment no longer reproduces")

    expected = assignment._certification_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"SK hynix Q2 product-assignment pointer mismatch: {key}")

    report_path = Path(str(pointer.get("report_path", "")))
    try:
        report_obj: object = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 product-assignment report is unreadable") from exc
    if report_obj != expected:
        raise ValueError("SK hynix Q2 product-assignment report payload mismatch")
    return reconstructed


__all__ = ["load_q2_product_assignment_certification"]
