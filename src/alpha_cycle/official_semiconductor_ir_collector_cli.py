"""Collect registered official semiconductor IR documents into auditable local packs."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    OfficialIrDocumentSpec,
    download_official_ir_document,
    load_official_ir_document_registry,
    parse_official_ir_document,
)

DEFAULT_OUTPUT = Path("data/private/live-research/official-semiconductor-ir")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _source_bytes(
    spec: OfficialIrDocumentSpec,
    local_document: Path | None,
    *,
    timeout_seconds: float,
) -> bytes:
    if local_document is None:
        return download_official_ir_document(spec, timeout_seconds=timeout_seconds)
    if not local_document.is_file():
        raise ValueError(f"Official IR local document not found: {local_document}")
    data = local_document.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Official IR local document is not a PDF")
    return data


def capture_official_ir_document(
    document_id: str,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_IR_DOCUMENT_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    local_document: str | Path | None = None,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    specs = load_official_ir_document_registry(registry_path)
    if document_id not in specs:
        raise ValueError(f"Official IR document_id is not registered: {document_id}")
    spec = specs[document_id]
    if spec.source_published_date > evaluation_date or spec.period_end > evaluation_date:
        raise ValueError("Official IR document is not observable by evaluation date")
    data = _source_bytes(
        spec,
        Path(local_document) if local_document is not None else None,
        timeout_seconds=timeout_seconds,
    )
    parsed = parse_official_ir_document(spec, data)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + spec.document_id
        + "__"
        + parsed.source_document_sha256[:12]
    )
    if directory.exists():
        raise ValueError(f"Official IR artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        source_path = temporary / "source_document.pdf"
        source_path.write_bytes(data)
        archived_source_path = str((directory / "source_document.pdf").resolve())

        baseline_facts = []
        for raw in parsed.baseline_facts:
            row = dict(raw)
            row["source_document_path"] = archived_source_path
            baseline_facts.append(row)
        forward_claims = []
        for raw in parsed.forward_input_claims:
            row = dict(raw)
            row["source_document_path"] = archived_source_path
            forward_claims.append(row)

        (temporary / "extracted_pages.json").write_text(
            json.dumps(list(parsed.pages), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temporary / "baseline_fact_pack.json").write_text(
            json.dumps({"facts": baseline_facts}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "forward_input_claim_pack.json").write_text(
            json.dumps({"claims": forward_claims}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "status": "official_semiconductor_ir_document_captured",
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "document_id": spec.document_id,
            "ticker": spec.ticker,
            "issuer_name": spec.issuer_name,
            "source_id": spec.source_id,
            "source_url": spec.source_url,
            "source_published_date": spec.source_published_date.isoformat(),
            "period_start": spec.period_start.isoformat(),
            "period_end": spec.period_end.isoformat(),
            "parser_id": spec.parser_id,
            "parser_semantics_certified": parsed.parser_semantics_certified,
            "source_document_sha256": parsed.source_document_sha256,
            "source_bytes_archived": True,
            "baseline_fact_count": len(parsed.baseline_facts),
            "forward_input_claim_count": len(parsed.forward_input_claims),
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": [
                "source_document.pdf",
                "extracted_pages.json",
                "baseline_fact_pack.json",
                "forward_input_claim_pack.json",
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
        "status": "official_semiconductor_ir_document_captured",
        "document_id": spec.document_id,
        "ticker": spec.ticker,
        "evaluation_date": evaluation_date.isoformat(),
        "source_document_sha256": parsed.source_document_sha256,
        "source_document_path": str((directory / "source_document.pdf").resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "baseline_fact_pack_path": str((directory / "baseline_fact_pack.json").resolve()),
        "forward_input_claim_pack_path": str(
            (directory / "forward_input_claim_pack.json").resolve()
        ),
        "source_bytes_archived": True,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / f"latest_{spec.document_id}.json"
    temporary_pointer = root / f".latest_{spec.document_id}.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-official-semiconductor-ir",
        description=(
            "Download only registered official issuer IR documents, archive bytes, and emit "
            "source-specific baseline/forward-input packs; parser drift fails closed"
        ),
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_IR_DOCUMENT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--local-document", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        result = capture_official_ir_document(
            args.document_id,
            evaluation_date=args.evaluation_date,
            registry_path=args.registry,
            output=args.output,
            local_document=args.local_document,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
