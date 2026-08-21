"""Offline verifier for archived SK hynix OpenDART Q2 product-revenue evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence import sk_hynix_opendart_product_revenue_parser_dispatch as _dispatch
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_source_consensus import (
    parse_periodic_product_revenue_source_consensus,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DiscoveredPeriodicProductRevenue,
    OpenDartPeriodicProductRevenueCertification,
    ProductRevenueMetrics,
    _payload,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_contract import (
    load_bound_periodic_product_revenue_parser_contract,
)
from alpha_cycle.intelligence.source_snapshot_asof import source_snapshot_date_as_of
from alpha_cycle.providers.opendart import CorpCode
from alpha_cycle.providers.opendart_documents import _parse_document_archive

parse_periodic_product_revenue_archive = _dispatch.parse_periodic_product_revenue_archive
parse_periodic_product_revenue_text = _dispatch.parse_periodic_product_revenue_text


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _certification(path: Path) -> OpenDartPeriodicProductRevenueCertification:
    payload = _object(path, "Periodic product revenue certification")
    metrics_raw = payload.get("metrics")
    if not isinstance(metrics_raw, dict):
        raise ValueError("Periodic product revenue certification metrics are invalid")
    metrics = ProductRevenueMetrics(
        unit=str(metrics_raw.get("unit", "")),
        dram_total=float(metrics_raw.get("dram_total", 0)),
        nand_and_solutions=float(metrics_raw.get("nand_and_solutions", 0)),
        other_products_services=float(metrics_raw.get("other_products_services", 0)),
        reported_company_revenue=float(metrics_raw.get("reported_company_revenue", 0)),
        direct_sum=float(metrics_raw.get("direct_sum", 0)),
        reconciliation_delta=float(metrics_raw.get("reconciliation_delta", 0)),
    )
    return OpenDartPeriodicProductRevenueCertification(
        evidence_id=str(payload.get("evidence_id", "")),
        evaluation_date=date.fromisoformat(str(payload.get("evaluation_date", ""))),
        document_id=str(payload.get("document_id", "")),
        ticker=str(payload.get("ticker", "")),
        issuer_name=str(payload.get("issuer_name", "")),
        rcept_no=str(payload.get("rcept_no", "")),
        report_name=str(payload.get("report_name", "")),
        receipt_date=date.fromisoformat(str(payload.get("receipt_date", ""))),
        period_start=date.fromisoformat(str(payload.get("period_start", ""))),
        period_end=date.fromisoformat(str(payload.get("period_end", ""))),
        metrics=metrics,
        archive_sha256=str(payload.get("archive_sha256", "")),
        archive_bytes=int(str(payload.get("archive_bytes", 0))),
        text_sha256=str(payload.get("text_sha256", "")),
        text_chars=int(str(payload.get("text_chars", 0))),
        source_url=str(payload.get("source_url", "")),
        source_receipt_certified=payload.get("source_receipt_certified") is True,
        source_archive_bytes_archived=payload.get("source_archive_bytes_archived") is True,
        source_vintage_certified=payload.get("source_vintage_certified") is True,
        current_quarter_period_certified=payload.get("current_quarter_period_certified") is True,
        direct_product_revenue_semantics_certified=(
            payload.get("direct_product_revenue_semantics_certified") is True
        ),
        other_amount_certified=payload.get("other_amount_certified") is True,
        company_revenue_reconciliation_certified=(
            payload.get("company_revenue_reconciliation_certified") is True
        ),
        product_revenue_baseline_eligible=(
            payload.get("product_revenue_baseline_eligible") is True
        ),
        allocation_resolver_registered=payload.get("allocation_resolver_registered") is True,
        product_profitability_certified=payload.get("product_profitability_certified") is True,
        numeric_forecast_enabled=payload.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=payload.get("fair_value_estimate_enabled") is True,
        target_price_enabled=payload.get("target_price_enabled") is True,
        decision_score_enabled=payload.get("decision_score_enabled") is True,
    )


def load_periodic_product_revenue_certification(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> OpenDartPeriodicProductRevenueCertification:
    pointer = _object(Path(pointer_path), "Periodic product revenue pointer")
    if pointer.get("status") != "skhynix_opendart_q2_product_revenue_certified":
        raise ValueError("Periodic product revenue pointer status is invalid")
    source_evaluation_date = source_snapshot_date_as_of(
        pointer.get("evaluation_date"),
        as_of_date=evaluation_date,
        label="Periodic product revenue evidence",
    )
    spec, _contract_hash = load_bound_periodic_product_revenue_parser_contract(pointer)

    certification = _certification(Path(str(pointer.get("certification_path", ""))))
    if certification.evaluation_date != source_evaluation_date:
        raise ValueError("Periodic product revenue certification evaluation date mismatch")
    if str(pointer.get("evidence_id", "")) != certification.evidence_id:
        raise ValueError("Periodic product revenue pointer/certification evidence mismatch")
    if certification.document_id != spec.document_id:
        raise ValueError("Periodic product revenue certification/contract document mismatch")
    if certification.ticker != spec.ticker or certification.issuer_name != spec.issuer_name:
        raise ValueError("Periodic product revenue certification/contract issuer mismatch")
    if certification.report_name != spec.report_name_exact:
        raise ValueError("Periodic product revenue certification/contract report mismatch")
    if (
        certification.period_start != spec.period_start
        or certification.period_end != spec.period_end
    ):
        raise ValueError("Periodic product revenue certification/contract period mismatch")

    archive_path = Path(str(pointer.get("archive_path", "")))
    try:
        archive_bytes = archive_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Periodic product revenue archived ZIP is missing") from exc
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != certification.archive_sha256:
        raise ValueError("Periodic product revenue archived ZIP hash mismatch")
    if archive_hash != str(pointer.get("archive_sha256", "")):
        raise ValueError("Periodic product revenue pointer archive hash mismatch")

    document = _parse_document_archive(
        archive_bytes,
        receipt=certification.rcept_no,
        retrieved_at=datetime.combine(source_evaluation_date, datetime.min.time(), tzinfo=UTC),
    )
    if document.text_sha256 != certification.text_sha256:
        raise ValueError("Periodic product revenue ZIP does not reproduce normalized text hash")
    normalized_path = Path(str(pointer.get("normalized_text_path", "")))
    try:
        persisted_text = normalized_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError("Periodic product revenue normalized text is missing") from exc
    if hashlib.sha256(persisted_text.encode("utf-8")).hexdigest() != certification.text_sha256:
        raise ValueError("Periodic product revenue normalized text hash mismatch")
    if persisted_text != document.text:
        raise ValueError("Periodic product revenue normalized text does not reproduce from ZIP")

    metrics = parse_periodic_product_revenue_source_consensus(
        spec,
        document.text,
        archive_bytes,
    )
    if metrics != certification.metrics:
        raise ValueError("Periodic product revenue source consensus output does not reproduce")
    structured_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
    if structured_metrics != certification.metrics:
        raise ValueError(
            "Periodic product revenue certified source structure does not reproduce metrics"
        )

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
        metrics,
        evaluation_date=source_evaluation_date,
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
        raise ValueError("Periodic product revenue certification evidence_id does not reproduce")
    return certification


__all__ = ["load_periodic_product_revenue_certification"]
