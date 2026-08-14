"""Capture source-bounded semiconductor provisional earnings from official OpenDART."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.opendart_provisional_earnings import (
    DEFAULT_PROVISIONAL_EARNINGS_REGISTRY,
    OpenDartProvisionalEarningsEvidence,
    collect_provisional_earnings,
    load_provisional_earnings_registry,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import DisclosureDocumentEvidence

DEFAULT_OUTPUT = Path("data/private/live-research/opendart-provisional-earnings")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _evidence_payload(evidence: OpenDartProvisionalEarningsEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "document_id": evidence.document_id,
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "rcept_no": evidence.rcept_no,
        "report_name": evidence.report_name,
        "receipt_date": evidence.receipt_date.isoformat(),
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "unit": evidence.metrics.unit,
        "revenue": evidence.metrics.revenue,
        "operating_income": evidence.metrics.operating_income,
        "net_income": evidence.metrics.net_income,
        "archive_sha256": evidence.archive_sha256,
        "archive_bytes": evidence.archive_bytes,
        "text_sha256": evidence.text_sha256,
        "text_chars": evidence.text_chars,
        "member_count": evidence.member_count,
        "text_member_count": evidence.text_member_count,
        "source_receipt_certified": True,
        "parser_semantics_certified": True,
        "provisional": True,
        "audited": False,
        "company_level_actual": True,
        "product_baseline_eligible": False,
        "source_archive_bytes_archived": False,
        "normalized_document_text_archived": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }


def _document_metadata(document: DisclosureDocumentEvidence) -> dict[str, object]:
    return {
        "rcept_no": document.rcept_no,
        "retrieved_at": document.retrieved_at.isoformat(),
        "archive_sha256": document.archive_sha256,
        "archive_bytes": document.archive_bytes,
        "member_count": document.member_count,
        "text_member_count": document.text_member_count,
        "uncompressed_bytes": document.uncompressed_bytes,
        "text_sha256": document.text_sha256,
        "text_chars": document.text_chars,
        "text_truncated": document.text_truncated,
        "members": [
            {
                "name": member.name,
                "sha256": member.sha256,
                "compressed_bytes": member.compressed_bytes,
                "uncompressed_bytes": member.uncompressed_bytes,
                "encoding": member.encoding,
                "text_chars": member.text_chars,
            }
            for member in document.members
        ],
        "warnings": list(document.warnings),
        "source_archive_bytes_archived": False,
        "normalized_document_text_archived": True,
    }


def capture_opendart_provisional_earnings(
    document_id: str,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_PROVISIONAL_EARNINGS_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    captured_at: datetime | None = None,
    client: OpenDartReadOnlyClient | None = None,
) -> dict[str, object]:
    specs = load_provisional_earnings_registry(registry_path)
    if document_id not in specs:
        raise ValueError(f"Provisional earnings document is not registered: {document_id}")
    live_client = client or OpenDartReadOnlyClient.from_env()
    evidence, document = collect_provisional_earnings(
        live_client,
        specs[document_id],
        evaluation_date=evaluation_date,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.date() < evidence.receipt_date:
        raise ValueError("Provisional earnings capture cannot predate official receipt")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Provisional earnings artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        evidence_payload = _evidence_payload(evidence)
        (temporary / "provisional_earnings.json").write_text(
            json.dumps(evidence_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "normalized_document.txt").write_text(document.text, encoding="utf-8")
        (temporary / "document_metadata.json").write_text(
            json.dumps(_document_metadata(document), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **evidence_payload,
            "schema_version": 1,
            "status": "opendart_provisional_earnings_captured",
            "captured_at": captured.isoformat(),
            "source_registry_path": str(Path(registry_path).resolve()),
            "files": [
                "provisional_earnings.json",
                "normalized_document.txt",
                "document_metadata.json",
            ],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "opendart_provisional_earnings_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "document_id": evidence.document_id,
        "ticker": evidence.ticker,
        "rcept_no": evidence.rcept_no,
        "manifest_path": str((directory / "manifest.json").resolve()),
        "provisional_earnings_path": str((directory / "provisional_earnings.json").resolve()),
        "normalized_document_path": str((directory / "normalized_document.txt").resolve()),
        "document_metadata_path": str((directory / "document_metadata.json").resolve()),
        "company_level_actual": True,
        "product_baseline_eligible": False,
        "source_archive_bytes_archived": False,
        "normalized_document_text_archived": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_opendart_provisional_earnings.json"
    temporary_pointer = root / ".latest_opendart_provisional_earnings.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-opendart-provisional-earnings",
        description=(
            "Discover one registered exact provisional-earnings disclosure through official "
            "OpenDART, parse company-level current-quarter actuals, and keep product baselines "
            "and decision scoring disabled"
        ),
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_PROVISIONAL_EARNINGS_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_opendart_provisional_earnings(
            args.document_id,
            evaluation_date=args.evaluation_date,
            registry_path=args.registry,
            output=args.output,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
