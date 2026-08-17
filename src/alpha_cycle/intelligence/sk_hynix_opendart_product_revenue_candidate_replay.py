"""Non-mutating replay of an existing SK hynix product-revenue certification.

This module is the safe precondition for reusing an already archived certification under a
newer parser/source contract.  It verifies the immutable source artifacts and replays both
normalized-text and structured-archive parsers against a caller-supplied current spec, but
it never rewrites the pointer or parser-contract files.  A caller may bind a new contract
only after this replay succeeds.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DiscoveredPeriodicProductRevenue,
    OpenDartPeriodicProductRevenueCertification,
    PeriodicProductRevenueSpec,
    _payload,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    _certification,
    _object,
)
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_documents import _parse_document_archive


def replay_periodic_product_revenue_certification_against_spec(
    pointer_path: str | Path,
    spec: PeriodicProductRevenueSpec,
    *,
    evaluation_date: date,
) -> OpenDartPeriodicProductRevenueCertification:
    """Replay existing immutable evidence against ``spec`` without changing any artifact."""

    path = Path(pointer_path)
    pointer = _object(path, "Periodic product revenue reuse candidate pointer")
    if pointer.get("status") != "skhynix_opendart_q2_product_revenue_certified":
        raise ValueError("Periodic product revenue reuse candidate pointer status is invalid")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Periodic product revenue reuse candidate evaluation date mismatch")

    certification = _certification(Path(str(pointer.get("certification_path", ""))))
    if certification.evaluation_date != evaluation_date:
        raise ValueError("Periodic product revenue reuse candidate certification date mismatch")
    if certification.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("Periodic product revenue reuse candidate evidence mismatch")
    if certification.document_id != spec.document_id:
        raise ValueError("Periodic product revenue reuse candidate document mismatch")
    if certification.ticker != spec.ticker or certification.issuer_name != spec.issuer_name:
        raise ValueError("Periodic product revenue reuse candidate issuer mismatch")
    if certification.report_name != spec.report_name_exact:
        raise ValueError("Periodic product revenue reuse candidate report mismatch")
    if (
        certification.period_start != spec.period_start
        or certification.period_end != spec.period_end
    ):
        raise ValueError("Periodic product revenue reuse candidate period mismatch")

    archive_path = Path(str(pointer.get("archive_path", "")))
    try:
        archive_bytes = archive_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Periodic product revenue reuse candidate ZIP is missing") from exc
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != certification.archive_sha256:
        raise ValueError("Periodic product revenue reuse candidate ZIP hash mismatch")
    if archive_hash != str(pointer.get("archive_sha256", "")):
        raise ValueError("Periodic product revenue reuse candidate pointer ZIP hash mismatch")
    if len(archive_bytes) != certification.archive_bytes:
        raise ValueError("Periodic product revenue reuse candidate ZIP byte count mismatch")

    document = _parse_document_archive(
        archive_bytes,
        receipt=certification.rcept_no,
        retrieved_at=datetime.combine(evaluation_date, datetime.min.time(), tzinfo=UTC),
    )
    if document.text_sha256 != certification.text_sha256:
        raise ValueError("Periodic product revenue reuse candidate text hash does not reproduce")
    if document.text_chars != certification.text_chars:
        raise ValueError("Periodic product revenue reuse candidate text length does not reproduce")

    normalized_path = Path(str(pointer.get("normalized_text_path", "")))
    try:
        persisted_text = normalized_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(
            "Periodic product revenue reuse candidate normalized text is missing"
        ) from exc
    if persisted_text != document.text:
        raise ValueError("Periodic product revenue reuse candidate normalized text diverged")
    if hashlib.sha256(persisted_text.encode("utf-8")).hexdigest() != certification.text_sha256:
        raise ValueError("Periodic product revenue reuse candidate persisted text hash mismatch")

    text_metrics = parse_periodic_product_revenue_text(spec, document.text)
    archive_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
    if text_metrics != certification.metrics:
        raise ValueError("Periodic product revenue reuse candidate text parser changed metrics")
    if archive_metrics != certification.metrics:
        raise ValueError("Periodic product revenue reuse candidate archive parser changed metrics")
    if text_metrics != archive_metrics:
        raise ValueError("Periodic product revenue reuse candidate parser paths disagree")

    discovery = DiscoveredPeriodicProductRevenue(
        spec=spec,
        corp=CorpCode(
            corp_code="00164779",
            corp_name="SK하이닉스",
            stock_code=certification.ticker,
            modify_date=certification.receipt_date,
        ),
        rcept_no=certification.rcept_no,
        report_name=certification.report_name,
        receipt_date=certification.receipt_date,
    )
    expected_payload = _payload(
        discovery,
        document,
        text_metrics,
        evaluation_date=evaluation_date,
    )
    expected_id = hashlib.sha256(
        json.dumps(
            expected_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if expected_id != certification.evidence_id:
        raise ValueError("Periodic product revenue reuse candidate evidence_id does not reproduce")
    return certification


__all__ = ["replay_periodic_product_revenue_certification_against_spec"]
