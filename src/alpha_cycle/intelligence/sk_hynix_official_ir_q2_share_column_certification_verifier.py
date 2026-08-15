"""Rebuild SK hynix 2Q26 share-column certification from verified geometry evidence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_share_column_certification as cert
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry_verifier import (
    load_q2_product_geometry,
)


def load_q2_share_column_certification(
    pointer_path: str | Path = cert.DEFAULT_Q2_SHARE_COLUMN_POINTER,
    *,
    evaluation_date: date,
) -> cert.OfficialIrQ2ShareColumnCertification:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 share-column pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 share-column pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_share_column_certified":
        raise ValueError("SK hynix Q2 share-column pointer status is invalid")
    if pointer.get("period_column_semantics_certified") is not True:
        raise ValueError("SK hynix Q2 period-column semantics must be certified")
    for flag in cert._REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 share-column certification requires {flag}=false")

    geometry_pointer = Path(str(pointer.get("geometry_pointer_path", "")))
    geometry_item = load_q2_product_geometry(
        geometry_pointer,
        evaluation_date=evaluation_date,
    )
    reconstructed = cert.build_q2_share_column_certification(geometry_item)
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 share-column certification no longer reproduces")

    expected = cert._certification_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"SK hynix Q2 share-column pointer mismatch: {key}")

    report_path = Path(str(pointer.get("report_path", "")))
    try:
        report_obj: object = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 share-column report is unreadable") from exc
    if report_obj != expected:
        raise ValueError("SK hynix Q2 share-column report payload mismatch")
    return reconstructed


__all__ = ["load_q2_share_column_certification"]
