"""Capture registered historical official-IR HTML without promoting it to live evidence."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from alpha_cycle.intelligence.semiconductor_historical_official_ir import (
    DEFAULT_HISTORICAL_IR_REGISTRY,
    HistoricalForwardClaim,
    HistoricalOfficialIrSpec,
    ParsedHistoricalOfficialIr,
    load_historical_official_ir_registry,
    parse_historical_official_ir,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-historical-official-ir")


def _download(spec: HistoricalOfficialIrSpec, *, timeout_seconds: float) -> bytes:
    request = Request(
        spec.source_url,
        headers={"User-Agent": "Alpha-Cycle-Lab/0.1 historical-official-ir-readonly"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        data = bytes(response.read())
    prefix = data[:4096].decode("utf-8", errors="ignore").casefold()
    if "<html" not in prefix and "<!doctype html" not in prefix:
        raise ValueError(f"Historical official IR source is not HTML: {spec.document_id}")
    return data


def _claim_row(
    parsed: ParsedHistoricalOfficialIr,
    claim: HistoricalForwardClaim,
) -> dict[str, object]:
    spec = parsed.spec
    return {
        "ticker": claim.ticker,
        "block_id": claim.block_id,
        "claim_type": "forward_driver",
        "metric_id": claim.metric_id,
        "evidence_kind": "qualitative",
        "statement": claim.statement,
        "numeric_value": None,
        "unit": None,
        "period_start": claim.period_start.isoformat(),
        "period_end": claim.period_end.isoformat(),
        "source_id": spec.source_id,
        "source_url": spec.source_url,
        "source_published_date": spec.source_published_date.isoformat(),
        "semantics_certified": True,
        "source_vintage_certified": False,
        "reuse_or_license_basis_documented": False,
        "source_document_sha256": parsed.source_document_sha256,
        "source_bytes_archived": True,
        "historical_vintage_certified": False,
        "current_forward_coverage_eligible": False,
    }


def capture_historical_official_ir(
    document_id: str,
    *,
    registry_path: str | Path = DEFAULT_HISTORICAL_IR_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
    source_bytes: bytes | None = None,
) -> dict[str, object]:
    specs = load_historical_official_ir_registry(registry_path)
    if document_id not in specs:
        raise ValueError(f"Historical official IR document is not registered: {document_id}")
    spec = specs[document_id]
    data = (
        source_bytes
        if source_bytes is not None
        else _download(spec, timeout_seconds=timeout_seconds)
    )
    parsed = parse_historical_official_ir(spec, data)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.date() < spec.source_published_date:
        raise ValueError("Historical official IR capture cannot predate publisher metadata")

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
        raise ValueError(f"Historical official IR artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "source_document.html").write_bytes(data)
        (temporary / "visible_text.txt").write_text(parsed.visible_text, encoding="utf-8")
        facts = [
            {"metric_id": item.metric_id, "value": item.value, "unit": item.unit}
            for item in parsed.company_facts
        ]
        claims = [_claim_row(parsed, item) for item in parsed.forward_claims]
        (temporary / "company_facts.json").write_text(
            json.dumps({"facts": facts}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "historical_forward_claims.json").write_text(
            json.dumps({"claims": claims}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "status": "historical_official_ir_captured",
            "captured_at": captured.isoformat(),
            "document_id": spec.document_id,
            "ticker": spec.ticker,
            "issuer_name": spec.issuer_name,
            "source_id": spec.source_id,
            "source_url": spec.source_url,
            "source_published_date": spec.source_published_date.isoformat(),
            "period_start": spec.period_start.isoformat(),
            "period_end": spec.period_end.isoformat(),
            "parser_id": spec.parser_id,
            "source_document_sha256": parsed.source_document_sha256,
            "source_bytes_archived": True,
            "company_fact_count": len(facts),
            "historical_forward_claim_count": len(claims),
            "historical_vintage_certified": False,
            "point_in_time_backtest_eligible": False,
            "current_forward_coverage_eligible": False,
            "current_refresh_eligible": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
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
        "status": "historical_official_ir_captured",
        "document_id": spec.document_id,
        "ticker": spec.ticker,
        "captured_at": captured.isoformat(),
        "source_document_sha256": parsed.source_document_sha256,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "source_document_path": str((directory / "source_document.html").resolve()),
        "company_facts_path": str((directory / "company_facts.json").resolve()),
        "historical_forward_claims_path": str(
            (directory / "historical_forward_claims.json").resolve()
        ),
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "current_forward_coverage_eligible": False,
        "current_refresh_eligible": False,
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
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-historical-official-ir",
        description=(
            "Archive a registered official historical issuer page for retrospective research; "
            "the evidence is never promoted to current live coverage or PIT history"
        ),
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_HISTORICAL_IR_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        result = capture_historical_official_ir(
            args.document_id,
            registry_path=args.registry,
            output=args.output,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
