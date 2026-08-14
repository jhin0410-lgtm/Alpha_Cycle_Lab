"""Capture validated semiconductor forward-input claims into local research artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY,
    SemiconductorForwardInputClaim,
    build_semiconductor_forward_input_evidence,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-forward-input-evidence")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "source_id": claim.source_id,
        "source_role": claim.source_role,
        "source_url": claim.source_url,
        "source_published_date": claim.source_published_date.isoformat(),
        "evaluation_date": claim.evaluation_date.isoformat(),
        "semantics_certified": claim.semantics_certified,
        "source_vintage_certified": claim.source_vintage_certified,
        "reuse_or_license_basis_documented": claim.reuse_or_license_basis_documented,
        "primary_source": claim.primary_source,
        "numeric_model_input_eligible": claim.numeric_model_input_eligible,
        "decision_score_enabled": False,
    }


def _prepare_claims(
    claims: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[tuple[str, str]],
    dict[str, tuple[Path, bytes]],
]:
    prepared: list[dict[str, object]] = []
    binding_seeds: list[tuple[str, str]] = []
    documents: dict[str, tuple[Path, bytes]] = {}
    for raw in claims:
        document_path = Path(str(raw.get("source_document_path", "")).strip())
        if not str(document_path) or not document_path.is_file():
            raise ValueError(f"Forward-input source document not found: {document_path}")
        parser_id = str(raw.get("parser_id", "")).strip()
        if not parser_id:
            raise ValueError("Forward-input source document requires parser_id")
        data = document_path.read_bytes()
        if not data:
            raise ValueError(f"Forward-input source document is empty: {document_path}")
        digest = hashlib.sha256(data).hexdigest()
        documents.setdefault(digest, (document_path, data))
        clean = {
            key: value
            for key, value in raw.items()
            if key
            not in {
                "source_document_path",
                "source_document_sha256",
                "source_bytes_archived",
                "archived_document_path",
                "parser_id",
            }
        }
        prepared.append(clean)
        binding_seeds.append((digest, parser_id))
    return prepared, binding_seeds, documents


def capture_forward_input_evidence(
    claims: list[dict[str, object]],
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    registry_file = Path(registry_path)
    registry = load_structural_source_registry(registry_file)
    prepared_claims, binding_seeds, documents = _prepare_claims(claims)
    evidence = build_semiconductor_forward_input_evidence(
        prepared_claims,
        registry,
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
        documents_dir = temporary / "source_documents"
        documents_dir.mkdir()
        archived_paths: dict[str, str] = {}
        for digest, (original, data) in sorted(documents.items()):
            suffix = original.suffix.lower() or ".bin"
            target = documents_dir / f"{digest}{suffix}"
            target.write_bytes(data)
            archived_paths[digest] = str((directory / "source_documents" / target.name).resolve())

        bindings = [
            {
                "claim_id": claim.claim_id,
                "source_document_sha256": digest,
                "archived_document_path": archived_paths[digest],
                "parser_id": parser_id,
                "source_bytes_archived": True,
            }
            for claim, (digest, parser_id) in zip(
                evidence.claims,
                binding_seeds,
                strict=True,
            )
        ]
        archived_registry = temporary / "source_registry.yaml"
        shutil.copy2(registry_file, archived_registry)
        registry_sha256 = _sha256_file(archived_registry)
        (temporary / "claims.json").write_text(
            json.dumps(
                [_claim_payload(claim) for claim in evidence.claims],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (temporary / "source_bindings.json").write_text(
            json.dumps(bindings, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        evidence.block_coverage.to_csv(temporary / "block_coverage.csv", index=False)
        evidence.issuer_coverage.to_csv(temporary / "issuer_coverage.csv", index=False)
        manifest = {
            "schema_version": 2,
            "status": "semiconductor_forward_input_evidence_captured",
            "evidence_id": evidence.evidence_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "claim_count": len(evidence.claims),
            "tickers": sorted({claim.ticker for claim in evidence.claims}),
            "input_path": str(Path(input_path).resolve()) if input_path else None,
            "source_registry_sha256": registry_sha256,
            "source_document_sha256s": sorted(documents),
            "source_bytes_archived": True,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": [
                "claims.json",
                "source_bindings.json",
                "block_coverage.csv",
                "issuer_coverage.csv",
                "source_registry.yaml",
                "source_documents/",
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
        "schema_version": 2,
        "status": "semiconductor_forward_input_evidence_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "claims_path": str((directory / "claims.json").resolve()),
        "source_bindings_path": str((directory / "source_bindings.json").resolve()),
        "block_coverage_path": str((directory / "block_coverage.csv").resolve()),
        "issuer_coverage_path": str((directory / "issuer_coverage.csv").resolve()),
        "source_registry_path": str((directory / "source_registry.yaml").resolve()),
        "source_registry_sha256": registry_sha256,
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
            "Archive source bytes, validate semiconductor baseline/forward-driver claims, and "
            "capture block coverage without enabling a numeric forecast"
        ),
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_forward_input_evidence(
            _load_claims(args.input),
            evaluation_date=args.evaluation_date,
            registry_path=args.registry,
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
