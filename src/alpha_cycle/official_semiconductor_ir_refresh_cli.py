"""Refresh current registered official semiconductor IR evidence and downstream packs."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
)
from alpha_cycle.intelligence.official_semiconductor_ir_refresh import (
    build_official_ir_refresh_plan,
)
from alpha_cycle.official_semiconductor_ir_collector_cli import (
    DEFAULT_OUTPUT as DEFAULT_DOCUMENT_OUTPUT,
)
from alpha_cycle.official_semiconductor_ir_collector_cli import capture_official_ir_document
from alpha_cycle.semiconductor_accounting_identity_cli import (
    DEFAULT_OUTPUT as DEFAULT_ACCOUNTING_OUTPUT,
)
from alpha_cycle.semiconductor_accounting_identity_cli import (
    capture_semiconductor_accounting_identity,
)
from alpha_cycle.semiconductor_baseline_reconciliation_cli import (
    DEFAULT_OUTPUT as DEFAULT_BASELINE_OUTPUT,
)
from alpha_cycle.semiconductor_baseline_reconciliation_cli import (
    capture_semiconductor_baseline_reconciliation,
)
from alpha_cycle.semiconductor_forward_input_cli import (
    DEFAULT_OUTPUT as DEFAULT_FORWARD_OUTPUT,
)
from alpha_cycle.semiconductor_forward_input_cli import capture_forward_input_evidence

DEFAULT_OUTPUT = Path("data/private/live-research/official-semiconductor-ir-refresh")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _json_rows(path: Path, key: str, label: str) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    values = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError(f"{label} requires {key} array")
    rows: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError(f"{label} rows must be objects")
        rows.append({str(k): v for k, v in cast(dict[object, object], value).items()})
    return rows


def refresh_official_semiconductor_ir(
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_IR_DOCUMENT_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    document_output: str | Path = DEFAULT_DOCUMENT_OUTPUT,
    baseline_output: str | Path = DEFAULT_BASELINE_OUTPUT,
    forward_output: str | Path = DEFAULT_FORWARD_OUTPUT,
    accounting_output: str | Path = DEFAULT_ACCOUNTING_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    plan = build_official_ir_refresh_plan(
        evaluation_date=evaluation_date,
        registry_path=registry_path,
    )
    collected: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    downstream_failures: list[dict[str, object]] = []
    all_facts: list[dict[str, object]] = []
    all_claims: list[dict[str, object]] = []
    samsung_document_pointer: Path | None = None
    for item in plan.issuers:
        if item.selected_document_id is None:
            continue
        try:
            result = capture_official_ir_document(
                item.selected_document_id,
                evaluation_date=evaluation_date,
                registry_path=registry_path,
                output=document_output,
                timeout_seconds=timeout_seconds,
            )
            facts = _json_rows(
                Path(str(result["baseline_fact_pack_path"])),
                "facts",
                "Official IR baseline pack",
            )
            claims = _json_rows(
                Path(str(result["forward_input_claim_pack_path"])),
                "claims",
                "Official IR forward-input pack",
            )
            all_facts.extend(facts)
            all_claims.extend(claims)
            if item.ticker == "005930":
                samsung_document_pointer = (
                    Path(document_output)
                    / f"latest_{item.selected_document_id}.json"
                )
            collected.append(
                {
                    "ticker": item.ticker,
                    "document_id": item.selected_document_id,
                    "period_end": (
                        item.selected_period_end.isoformat() if item.selected_period_end else None
                    ),
                    "source_document_sha256": result["source_document_sha256"],
                    "artifact_directory": result["artifact_directory"],
                    "baseline_fact_count": len(facts),
                    "forward_input_claim_count": len(claims),
                }
            )
        except (OSError, TypeError, ValueError) as exc:
            failed.append(
                {
                    "ticker": item.ticker,
                    "document_id": item.selected_document_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    baseline_result: dict[str, object] | None = None
    forward_result: dict[str, object] | None = None
    accounting_result: dict[str, object] | None = None
    if all_facts:
        baseline_result = capture_semiconductor_baseline_reconciliation(
            all_facts,
            evaluation_date=evaluation_date,
            output=baseline_output,
        )
    if all_claims:
        forward_result = capture_forward_input_evidence(
            all_claims,
            evaluation_date=evaluation_date,
            output=forward_output,
        )
    if samsung_document_pointer is not None:
        try:
            accounting_result = capture_semiconductor_accounting_identity(
                samsung_document_pointer,
                evaluation_date=evaluation_date,
                output=accounting_output,
            )
        except (OSError, TypeError, ValueError) as exc:
            downstream_failures.append(
                {
                    "ticker": "005930",
                    "layer": "accounting_identity",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    unresolved = [
        {
            "ticker": item.ticker,
            "issuer_name": item.issuer_name,
            "status": item.status,
            "reason": item.reason,
        }
        for item in plan.issuers
        if item.selected_document_id is None
    ]
    status = (
        "complete"
        if collected
        and not failed
        and not downstream_failures
        and not unresolved
        else "partial"
        if collected
        else "unavailable"
    )
    baseline_pointer = (
        Path(str(baseline_result["artifact_directory"])).parent
        / "latest_semiconductor_baseline_reconciliation.json"
        if baseline_result
        else None
    )
    forward_pointer = (
        Path(str(forward_result["artifact_directory"])).parent
        / "latest_semiconductor_forward_input_evidence.json"
        if forward_result
        else None
    )
    accounting_pointer = (
        Path(str(accounting_result["artifact_directory"])).parent
        / "latest_semiconductor_accounting_identity.json"
        if accounting_result
        else None
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "captured_at": captured.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "selected_document_ids": list(plan.selected_document_ids),
        "collected": collected,
        "failed": failed,
        "downstream_failures": downstream_failures,
        "unresolved": unresolved,
        "baseline_reconciliation_pointer": str(baseline_pointer) if baseline_pointer else None,
        "forward_input_pointer": str(forward_pointer) if forward_pointer else None,
        "accounting_identity_pointer": str(accounting_pointer) if accounting_pointer else None,
        "operating_assumptions_generated": False,
        "scenario_probabilities_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    filename = root / "latest_official_semiconductor_ir_refresh.json"
    temporary = root / ".latest_official_semiconductor_ir_refresh.json.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(filename)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-official-semiconductor-ir-refresh",
        description=(
            "Collect each issuer's latest observable registered official IR document and build "
            "baseline/forward/accounting-identity evidence; unresolved issuers stay explicit "
            "and assumptions are not generated"
        ),
    )
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_IR_DOCUMENT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--document-output", type=Path, default=DEFAULT_DOCUMENT_OUTPUT)
    parser.add_argument("--baseline-output", type=Path, default=DEFAULT_BASELINE_OUTPUT)
    parser.add_argument("--forward-output", type=Path, default=DEFAULT_FORWARD_OUTPUT)
    parser.add_argument("--accounting-output", type=Path, default=DEFAULT_ACCOUNTING_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        result = refresh_official_semiconductor_ir(
            evaluation_date=args.evaluation_date,
            registry_path=args.registry,
            output=args.output,
            document_output=args.document_output,
            baseline_output=args.baseline_output,
            forward_output=args.forward_output,
            accounting_output=args.accounting_output,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] in {"complete", "partial"} else 2
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
