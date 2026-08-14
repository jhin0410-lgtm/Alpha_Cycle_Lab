"""Capture validated semiconductor forward-input claims into local research artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    SemiconductorForwardInputClaim,
    build_semiconductor_forward_input_evidence,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-forward-input-evidence")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _load_claims(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Forward-input claim pack not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Forward-input claim pack is invalid JSON: {path}") from exc
    raw_claims = payload.get("claims") if isinstance(payload, dict) else payload
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("Forward-input claim pack requires a non-empty claims array")
    claims: list[dict[str, object]] = []
    for value in raw_claims:
        if not isinstance(value, dict):
            raise ValueError("Forward-input claim must be an object")
        claims.append({str(key): item for key, item in cast(dict[object, object], value).items()})
    return claims


def _claim_payload(claim: SemiconductorForwardInputClaim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "ticker": claim.ticker,
        "block_id": claim.block_id,
        "claim_type": claim.claim_type,
        "metric_id": claim.metric_id,
        "evidence_kind": claim.evidence_kind,
        "statement": claim.statement,
        "numeric_value": claim.numeric_value,
        "unit": claim.unit,
        "period_start": claim.period_start.isoformat() if claim.period_start else None,
        "period_end": claim.period_end.isoformat() if claim.period_end else None,
        "source_role": claim.source_role,
        "source_url": claim.source_url,
        "source_published_date": claim.source_published_date.isoformat(),
        "evaluation_date": claim.evaluation_date.isoformat(),
        "semantics_certified": claim.semantics_certified,
        "source_vintage_certified": claim.source_vintage_certified,
        "reuse_or_license_basis_documented": claim.reuse_or_license_basis_documented,
        "primary_source": claim.primary_source,
        "decision_score_enabled": False,
    }


def capture_forward_input_evidence(
    claims: list[dict[str, object]],
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    evidence = build_semiconductor_forward_input_evidence(
        claims,
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
        raise ValueError(f"Forward-input artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "claims.json").write_text(
            json.dumps(
                [_claim_payload(claim) for claim in evidence.claims],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        evidence.block_coverage.to_csv(temporary / "block_coverage.csv", index=False)
        evidence.issuer_coverage.to_csv(temporary / "issuer_coverage.csv", index=False)
        manifest = {
            "schema_version": 1,
            "status": "semiconductor_forward_input_evidence_captured",
            "evidence_id": evidence.evidence_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "claim_count": len(evidence.claims),
            "tickers": sorted({claim.ticker for claim in evidence.claims}),
            "input_path": str(Path(input_path).resolve()) if input_path else None,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": ["claims.json", "block_coverage.csv", "issuer_coverage.csv"],
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
        "status": "semiconductor_forward_input_evidence_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "claims_path": str((directory / "claims.json").resolve()),
        "block_coverage_path": str((directory / "block_coverage.csv").resolve()),
        "issuer_coverage_path": str((directory / "issuer_coverage.csv").resolve()),
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_semiconductor_forward_input_evidence.json"
    temporary_pointer = root / ".latest_semiconductor_forward_input_evidence.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-forward-input",
        description=(
            "Validate source-bounded semiconductor baseline/forward-driver claims and "
            "capture block coverage without enabling a numeric forecast"
        ),
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_forward_input_evidence(
            _load_claims(args.input),
            evaluation_date=args.evaluation_date,
            output=args.output,
            input_path=args.input,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
