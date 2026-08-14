"""Capture validated semiconductor structural evidence packs as local research artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    SemiconductorStructuralClaim,
    build_structural_evidence_bundle,
    load_structural_source_registry,
)

DEFAULT_REGISTRY = Path("config/semiconductor_structural_sources.yaml")
DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-structural-evidence")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _load_claims(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Structural evidence input not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Structural evidence input is not valid JSON: {path}") from exc
    if isinstance(payload, dict):
        raw_claims = payload.get("claims")
    else:
        raw_claims = payload
    if not isinstance(raw_claims, list) or not raw_claims:
        raise ValueError("Structural evidence input must contain a non-empty claims array")
    claims: list[dict[str, object]] = []
    for value in raw_claims:
        if not isinstance(value, dict):
            raise ValueError("Each structural evidence claim must be an object")
        claims.append({str(key): item for key, item in cast(dict[object, object], value).items()})
    return claims


def _claim_payload(claim: SemiconductorStructuralClaim) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "subject": claim.subject,
        "dimension": claim.dimension,
        "as_of_date": claim.as_of_date.isoformat(),
        "source_id": claim.source_id,
        "source_url": claim.source_url,
        "source_published_date": claim.source_published_date.isoformat(),
        "evidence_kind": claim.evidence_kind,
        "statement": claim.statement,
        "numeric_value": claim.numeric_value,
        "unit": claim.unit,
        "product_scope": claim.product_scope,
        "semantics_certified": claim.semantics_certified,
        "reuse_basis_documented": claim.reuse_basis_documented,
        "issuer_specific": claim.issuer_specific,
        "decision_score_enabled": False,
    }


def _write_bundle(
    output: Path,
    *,
    evaluation_date: date,
    registry_path: Path,
    input_path: Path,
    claims: list[dict[str, object]],
) -> dict[str, object]:
    registry = load_structural_source_registry(registry_path)
    bundle = build_structural_evidence_bundle(
        claims,
        registry,
        evaluation_date=evaluation_date,
    )
    captured_at = datetime.now(UTC)
    directory = output / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__" + bundle.bundle_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Structural evidence artifact already exists: {directory}")
    temporary = output / f".{directory.name}.tmp"
    output.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        claims_payload = [_claim_payload(claim) for claim in bundle.claims]
        (temporary / "claims.json").write_text(
            json.dumps(claims_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "status": "semiconductor_structural_evidence_captured",
            "bundle_id": bundle.bundle_id,
            "captured_at": captured_at.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "claim_count": len(bundle.claims),
            "dimensions": sorted({claim.dimension for claim in bundle.claims}),
            "subjects": sorted({claim.subject for claim in bundle.claims}),
            "source_ids": sorted({claim.source_id for claim in bundle.claims}),
            "registry_path": str(registry_path.resolve()),
            "input_path": str(input_path.resolve()),
            "source_bytes_archived": False,
            "historical_snapshot_certified": False,
            "numeric_memory_price_signal_enabled": False,
            "decision_score_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": ["claims.json"],
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
        "status": "semiconductor_structural_evidence_captured",
        "bundle_id": bundle.bundle_id,
        "evaluation_date": evaluation_date.isoformat(),
        "claim_count": len(bundle.claims),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "claims_path": str((directory / "claims.json").resolve()),
        "source_bytes_archived": False,
        "historical_snapshot_certified": False,
        "numeric_memory_price_signal_enabled": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = output / "latest_semiconductor_structural_evidence.json"
    temporary_pointer = output / ".latest_semiconductor_structural_evidence.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-structural-evidence",
        description=(
            "Validate and capture primary-source semiconductor structural evidence; "
            "does not scrape webpages or enable decision scoring"
        ),
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not args.registry.is_file():
            raise ValueError(f"Structural source registry not found: {args.registry}")
        claims = _load_claims(args.input)
        result = _write_bundle(
            args.output,
            evaluation_date=args.evaluation_date,
            registry_path=args.registry,
            input_path=args.input,
            claims=claims,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
