"""Capture pinned SEC company-level actual evidence into auditable local artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sec_company_actual import (
    DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
    SecCompanyActualEvidence,
    collect_sec_company_actual,
    load_sec_company_actual_registry,
)

DEFAULT_OUTPUT = Path("data/private/live-research/sec-company-actual")
DEFAULT_POINTER = DEFAULT_OUTPUT / "latest_sec_company_actual.json"
_FALSE_FLAGS = {
    "audited": False,
    "product_baseline_eligible": False,
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


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _payload(evidence: SecCompanyActualEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "document_id": evidence.document_id,
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "accession_number": evidence.accession_number,
        "primary_document": evidence.primary_document,
        "filing_date": evidence.filing_date.isoformat(),
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "submissions_url": evidence.submissions_url,
        "filing_url": evidence.filing_url,
        "submissions_sha256": evidence.submissions_sha256,
        "filing_sha256": evidence.filing_sha256,
        "unit": evidence.metrics.unit,
        "revenue": evidence.metrics.revenue,
        "operating_income": evidence.metrics.operating_income,
        "net_income": evidence.metrics.net_income,
        "company_level_actual": True,
        "provisional": True,
        "source_bytes_archived": True,
        **_FALSE_FLAGS,
    }


def capture_sec_company_actual(
    document_id: str,
    *,
    evaluation_date: date,
    user_agent: str,
    registry_path: str | Path = DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    specs = load_sec_company_actual_registry(registry_path)
    if document_id not in specs:
        raise ValueError(f"SEC company actual document_id is not registered: {document_id}")
    evidence, submissions_bytes, filing_bytes = collect_sec_company_actual(
        specs[document_id],
        evaluation_date=evaluation_date,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.document_id
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"SEC company actual artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "submissions.json").write_bytes(submissions_bytes)
        (temporary / "filing.html").write_bytes(filing_bytes)
        payload = _payload(evidence)
        (temporary / "company_actual.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "sec_company_actual_captured",
            "captured_at": captured.isoformat(),
            "declared_user_agent_supplied": True,
            "files": ["submissions.json", "filing.html", "company_actual.json"],
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
        **_payload(evidence),
        "schema_version": 1,
        "status": "sec_company_actual_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "company_actual_path": str((directory / "company_actual.json").resolve()),
        "submissions_path": str((directory / "submissions.json").resolve()),
        "filing_path": str((directory / "filing.html").resolve()),
    }
    pointer_path = root / "latest_sec_company_actual.json"
    temporary_pointer = root / ".latest_sec_company_actual.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-sec-company-actual",
        description=(
            "Discover a pinned official SEC filing, archive submissions/filing bytes, and "
            "emit non-product company-level actual evidence"
        ),
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument(
        "--user-agent",
        default=os.getenv("SEC_EDGAR_USER_AGENT", ""),
        help="Declared SEC EDGAR user agent; defaults to SEC_EDGAR_USER_AGENT",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not args.user_agent:
            raise ValueError("SEC_EDGAR_USER_AGENT or --user-agent is required")
        result = capture_sec_company_actual(
            args.document_id,
            evaluation_date=args.evaluation_date,
            user_agent=args.user_agent,
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
