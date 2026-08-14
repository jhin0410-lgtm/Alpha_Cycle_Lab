"""Archive issuer accounting source bytes and capture direct-fact baseline bridges."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_baseline_reconciliation import (
    DEFAULT_BASELINE_SOURCE_REGISTRY,
    SemiconductorBaselineFact,
    build_semiconductor_baseline_reconciliation,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-baseline-reconciliation")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_facts(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Baseline fact pack not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Baseline fact pack is invalid JSON: {path}") from exc
    values = payload.get("facts") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not values:
        raise ValueError("Baseline fact pack requires a non-empty facts array")
    rows: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("Baseline fact rows must be objects")
        rows.append({str(key): item for key, item in cast(dict[object, object], value).items()})
    return rows


def _prepare_facts(
    raw_facts: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, tuple[Path, bytes]]]:
    prepared: list[dict[str, object]] = []
    documents: dict[str, tuple[Path, bytes]] = {}
    for raw in raw_facts:
        source_document_path = Path(str(raw.get("source_document_path", "")).strip())
        if not str(source_document_path) or not source_document_path.is_file():
            raise ValueError(f"Baseline source document not found: {source_document_path}")
        data = source_document_path.read_bytes()
        if not data:
            raise ValueError(f"Baseline source document is empty: {source_document_path}")
        digest = _sha256_bytes(data)
        documents.setdefault(digest, (source_document_path, data))
        row = {key: value for key, value in raw.items() if key != "source_document_path"}
        row["source_document_sha256"] = digest
        row["source_bytes_archived"] = True
        row["source_vintage_certified"] = True
        prepared.append(row)
    return prepared, documents


def _fact_payload(
    fact: SemiconductorBaselineFact,
    archived_document_path: str,
) -> dict[str, object]:
    return {
        "fact_id": fact.fact_id,
        "ticker": fact.ticker,
        "scope_id": fact.scope_id,
        "metric_id": fact.metric_id,
        "value": fact.value,
        "unit": fact.unit,
        "period_start": fact.period_start.isoformat(),
        "period_end": fact.period_end.isoformat(),
        "source_id": fact.source_id,
        "source_url": fact.source_url,
        "source_published_date": fact.source_published_date.isoformat(),
        "source_document_sha256": fact.source_document_sha256,
        "archived_document_path": archived_document_path,
        "source_bytes_archived": fact.source_bytes_archived,
        "semantics_certified": fact.semantics_certified,
        "source_vintage_certified": fact.source_vintage_certified,
        "primary_source": fact.primary_source,
        "bridge_eligible": fact.bridge_eligible,
        "decision_score_enabled": False,
    }


def capture_semiconductor_baseline_reconciliation(
    raw_facts: list[dict[str, object]],
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_BASELINE_SOURCE_REGISTRY,
    output: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    registry_file = Path(registry_path)
    registry = load_structural_source_registry(registry_file)
    prepared, documents = _prepare_facts(raw_facts)
    evidence = build_semiconductor_baseline_reconciliation(
        prepared,
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
        raise ValueError(f"Baseline reconciliation artifact already exists: {directory}")
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

        archived_registry = temporary / "source_registry.yaml"
        shutil.copy2(registry_file, archived_registry)
        registry_sha256 = _sha256_file(archived_registry)
        (temporary / "facts.json").write_text(
            json.dumps(
                [
                    _fact_payload(fact, archived_paths[fact.source_document_sha256])
                    for fact in evidence.facts
                ],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        evidence.bridge_coverage.to_csv(temporary / "bridge_coverage.csv", index=False)
        evidence.issuer_summary.to_csv(temporary / "issuer_summary.csv", index=False)
        manifest = {
            "schema_version": 1,
            "status": "semiconductor_baseline_reconciliation_captured",
            "evidence_id": evidence.evidence_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "fact_count": len(evidence.facts),
            "document_sha256s": sorted(documents),
            "source_registry_sha256": registry_sha256,
            "input_path": str(Path(input_path).resolve()) if input_path else None,
            "residual_derivation_enabled": False,
            "internal_estimate_enabled": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": [
                "facts.json",
                "bridge_coverage.csv",
                "issuer_summary.csv",
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
        "schema_version": 1,
        "status": "semiconductor_baseline_reconciliation_captured",
        "evidence_id": evidence.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "facts_path": str((directory / "facts.json").resolve()),
        "bridge_coverage_path": str((directory / "bridge_coverage.csv").resolve()),
        "issuer_summary_path": str((directory / "issuer_summary.csv").resolve()),
        "source_registry_path": str((directory / "source_registry.yaml").resolve()),
        "source_registry_sha256": registry_sha256,
        "residual_derivation_enabled": False,
        "internal_estimate_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_semiconductor_baseline_reconciliation.json"
    temporary_pointer = root / ".latest_semiconductor_baseline_reconciliation.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-baseline-reconciliation",
        description=(
            "Archive issuer accounting source bytes and certify only direct same-scope baseline "
            "bridges; no residual arithmetic or internal estimates are permitted"
        ),
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_BASELINE_SOURCE_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_semiconductor_baseline_reconciliation(
            _load_facts(args.input),
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
