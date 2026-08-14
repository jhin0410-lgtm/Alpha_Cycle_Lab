"""Build Samsung company-level accounting identity evidence from archived official IR bytes."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.semiconductor_accounting_identity import (
    SamsungAccountingIdentityEvidence,
    build_samsung_accounting_identity_from_official_ir,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-accounting-identity")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _payload(evidence: SamsungAccountingIdentityEvidence) -> dict[str, object]:
    return {
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "ticker": "005930",
        "source_document_sha256": evidence.source_document_sha256,
        "consolidated_revenue": evidence.consolidated_revenue,
        "segment_revenue_sum": evidence.segment_revenue_sum,
        "consolidation_revenue_adjustment": evidence.consolidation_revenue_adjustment,
        "consolidated_operating_income": evidence.consolidated_operating_income,
        "segment_operating_income_sum": evidence.segment_operating_income_sum,
        "consolidation_operating_income_adjustment": (
            evidence.consolidation_operating_income_adjustment
        ),
        "profit_before_tax": evidence.profit_before_tax,
        "income_tax": evidence.income_tax,
        "net_income": evidence.net_income,
        "non_operating_to_pbt_bridge": evidence.non_operating_to_pbt_bridge,
        "corporate_consolidation_bridge_certified": (
            evidence.corporate_consolidation_bridge_certified
        ),
        "net_income_bridge_certified": evidence.net_income_bridge_certified,
        "corporate_baseline_bridge_certified": evidence.corporate_baseline_bridge_certified,
        "accounting_identity_derivation_enabled": True,
        "residual_estimate_enabled": False,
        "segment_profit_inference_enabled": False,
        "memory_operating_income_derived": False,
        "foundry_operating_income_derived": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }


def capture_semiconductor_accounting_identity(
    official_ir_pointer: str | Path,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence = build_samsung_accounting_identity_from_official_ir(
        official_ir_pointer,
        evaluation_date=evaluation_date,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Accounting identity artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        evidence_payload = _payload(evidence)
        (temporary / "accounting_identity.json").write_text(
            json.dumps(evidence_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **evidence_payload,
            "schema_version": 1,
            "status": "semiconductor_accounting_identity_captured",
            "captured_at": captured.isoformat(),
            "official_ir_pointer_path": str(Path(official_ir_pointer).resolve()),
            "files": ["accounting_identity.json"],
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
        "status": "semiconductor_accounting_identity_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "ticker": "005930",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "accounting_identity_path": str((directory / "accounting_identity.json").resolve()),
        "corporate_baseline_bridge_certified": evidence.corporate_baseline_bridge_certified,
        "accounting_identity_derivation_enabled": True,
        "residual_estimate_enabled": False,
        "segment_profit_inference_enabled": False,
        "memory_operating_income_derived": False,
        "foundry_operating_income_derived": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_semiconductor_accounting_identity.json"
    temporary_pointer = root / ".latest_semiconductor_accounting_identity.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-accounting-identity",
        description=(
            "Build source-bounded company accounting identities from an archived official "
            "Samsung IR document without enabling residual segment-profit estimates"
        ),
    )
    parser.add_argument("--official-ir-pointer", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_semiconductor_accounting_identity(
            args.official_ir_pointer,
            evaluation_date=args.evaluation_date,
            output=args.output,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
