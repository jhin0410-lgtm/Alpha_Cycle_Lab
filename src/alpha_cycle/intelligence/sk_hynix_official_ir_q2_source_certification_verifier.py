"""Rebuild SK hynix 2Q26 source certification from archived official PDF bytes."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_source_certification as cert
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    load_q2_attachment_evidence,
)


def load_q2_source_certification(
    pointer_path: str | Path = cert.DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER,
    *,
    evaluation_date: date,
) -> cert.OfficialIrQ2SourceCertification:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 source-certification pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 source-certification pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_source_certification_captured":
        raise ValueError("SK hynix Q2 source-certification pointer status is invalid")
    for flag in cert._REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 source-certification requires {flag}=false")

    attachment_pointer = Path(str(pointer.get("attachment_pointer_path", "")))
    evidence = load_q2_attachment_evidence(
        attachment_pointer,
        evaluation_date=evaluation_date,
    )
    try:
        attachment_obj: object = json.loads(attachment_pointer.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError(
            "SK hynix Q2 attachment pointer is unreadable during certification"
        ) from exc
    if not isinstance(attachment_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pdf_path = Path(str(attachment_obj.get("pdf_path", "")))
    pdf_bytes = pdf_path.read_bytes()
    if hashlib.sha256(pdf_bytes).hexdigest() != evidence.pdf_sha256:
        raise ValueError("SK hynix Q2 certification archived PDF hash mismatch")

    reconstructed = cert.build_q2_source_certification(evidence, pdf_bytes=pdf_bytes)
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 source certification no longer reproduces")

    expected = cert._certification_payload(reconstructed)
    for key, value in expected.items():
        if pointer.get(key) != value:
            raise ValueError(f"SK hynix Q2 source-certification pointer mismatch: {key}")

    report_path = Path(str(pointer.get("report_path", "")))
    try:
        report_obj: object = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 source-certification report is unreadable") from exc
    if report_obj != expected:
        raise ValueError("SK hynix Q2 source-certification report payload mismatch")
    return reconstructed


__all__ = ["load_q2_source_certification"]
