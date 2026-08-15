"""Bind OpenDART product-revenue artifacts to the exact parser/source contract used."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def periodic_product_revenue_contract_payload(
    spec: PeriodicProductRevenueSpec,
) -> dict[str, object]:
    """Return a canonical, JSON-safe parser/source contract for one evidence capture."""

    return {
        "schema_version": 1,
        "document_id": spec.document_id,
        "ticker": spec.ticker,
        "issuer_name": spec.issuer_name,
        "source_id": spec.source_id,
        "report_name_exact": spec.report_name_exact,
        "discovery_begin_date": spec.discovery_begin_date.isoformat(),
        "discovery_end_date": spec.discovery_end_date.isoformat(),
        "period_start": spec.period_start.isoformat(),
        "period_end": spec.period_end.isoformat(),
        "parser_id": spec.parser_id,
        "expected_identity_anchors": list(spec.expected_identity_anchors),
        "product_labels": {
            key: list(values)
            for key, values in sorted(spec.product_labels.items())
        },
    }


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def periodic_product_revenue_contract_sha256(
    spec: PeriodicProductRevenueSpec,
) -> str:
    return hashlib.sha256(
        _canonical_bytes(periodic_product_revenue_contract_payload(spec))
    ).hexdigest()


def product_revenue_chain_evidence_id(
    certification_evidence_id: str,
    parser_contract_sha256: str,
) -> str:
    if len(certification_evidence_id) != 64 or len(parser_contract_sha256) != 64:
        raise ValueError("Product revenue evidence/contract hashes must be SHA-256")
    payload = {
        "certification_evidence_id": certification_evidence_id,
        "parser_contract_sha256": parser_contract_sha256,
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def bind_periodic_product_revenue_parser_contract(
    pointer_path: str | Path,
    spec: PeriodicProductRevenueSpec,
) -> dict[str, object]:
    """Archive the exact parser contract and atomically bind it to a capture pointer."""

    path = Path(pointer_path)
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Periodic product revenue pointer not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Periodic product revenue pointer is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("Periodic product revenue pointer must be a JSON object")
    pointer = {str(key): value for key, value in cast(dict[object, object], raw).items()}
    if pointer.get("status") != "skhynix_opendart_q2_product_revenue_certified":
        raise ValueError("Periodic product revenue pointer status is invalid")
    if str(pointer.get("evidence_id", "")) == "":
        raise ValueError("Periodic product revenue pointer lacks evidence_id")
    certification_path = Path(str(pointer.get("certification_path", "")))
    if not certification_path.is_file():
        raise ValueError("Periodic product revenue certification file is missing")

    contract = periodic_product_revenue_contract_payload(spec)
    contract_hash = periodic_product_revenue_contract_sha256(spec)
    contract_path = certification_path.parent / "parser_contract.json"
    temporary_contract = certification_path.parent / ".parser_contract.json.tmp"
    temporary_contract.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if hashlib.sha256(_canonical_bytes(contract)).hexdigest() != contract_hash:
        temporary_contract.unlink(missing_ok=True)
        raise ValueError("Periodic product revenue parser contract hash diverged")
    temporary_contract.replace(contract_path)

    chain_id = product_revenue_chain_evidence_id(
        str(pointer["evidence_id"]),
        contract_hash,
    )
    pointer.update(
        {
            "parser_contract_bound": True,
            "parser_contract_path": str(contract_path),
            "parser_contract_sha256": contract_hash,
            "chain_evidence_id": chain_id,
        }
    )
    temporary_pointer = path.with_name(f".{path.name}.tmp")
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(path)
    return pointer


def periodic_product_revenue_spec_from_contract(
    payload: object,
) -> PeriodicProductRevenueSpec:
    if not isinstance(payload, dict):
        raise ValueError("Periodic product revenue parser contract must be an object")
    raw = cast(dict[object, object], payload)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported periodic product revenue parser-contract schema")
    anchors = raw.get("expected_identity_anchors")
    labels = raw.get("product_labels")
    if not isinstance(anchors, list) or not isinstance(labels, dict):
        raise ValueError("Periodic product revenue parser contract is incomplete")
    normalized_labels: dict[str, tuple[str, ...]] = {}
    for key, value in cast(dict[object, object], labels).items():
        if not isinstance(value, list):
            raise ValueError("Periodic product revenue parser labels must be arrays")
        normalized = tuple(str(item).strip() for item in value if str(item).strip())
        if not normalized:
            raise ValueError("Periodic product revenue parser label set cannot be empty")
        normalized_labels[str(key)] = normalized
    return PeriodicProductRevenueSpec(
        document_id=str(raw.get("document_id", "")),
        ticker=str(raw.get("ticker", "")),
        issuer_name=str(raw.get("issuer_name", "")),
        source_id=str(raw.get("source_id", "")),
        report_name_exact=str(raw.get("report_name_exact", "")),
        discovery_begin_date=date.fromisoformat(str(raw.get("discovery_begin_date", ""))),
        discovery_end_date=date.fromisoformat(str(raw.get("discovery_end_date", ""))),
        period_start=date.fromisoformat(str(raw.get("period_start", ""))),
        period_end=date.fromisoformat(str(raw.get("period_end", ""))),
        parser_id=str(raw.get("parser_id", "")),
        expected_identity_anchors=tuple(
            str(item).strip() for item in anchors if str(item).strip()
        ),
        product_labels=normalized_labels,
    )


def load_bound_periodic_product_revenue_parser_contract(
    pointer: dict[str, object],
) -> tuple[PeriodicProductRevenueSpec, str]:
    if pointer.get("parser_contract_bound") is not True:
        raise ValueError("Periodic product revenue parser contract is not bound")
    contract_path = Path(str(pointer.get("parser_contract_path", "")))
    try:
        payload: object = json.loads(contract_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("Periodic product revenue parser contract is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Periodic product revenue parser contract is invalid JSON") from exc
    spec = periodic_product_revenue_spec_from_contract(payload)
    canonical = periodic_product_revenue_contract_payload(spec)
    contract_hash = hashlib.sha256(_canonical_bytes(canonical)).hexdigest()
    if contract_hash != str(pointer.get("parser_contract_sha256", "")):
        raise ValueError("Periodic product revenue parser contract hash mismatch")
    expected_chain = product_revenue_chain_evidence_id(
        str(pointer.get("evidence_id", "")),
        contract_hash,
    )
    if expected_chain != str(pointer.get("chain_evidence_id", "")):
        raise ValueError("Periodic product revenue chain evidence_id mismatch")
    return spec, contract_hash


__all__ = [
    "bind_periodic_product_revenue_parser_contract",
    "load_bound_periodic_product_revenue_parser_contract",
    "periodic_product_revenue_contract_payload",
    "periodic_product_revenue_contract_sha256",
    "periodic_product_revenue_spec_from_contract",
    "product_revenue_chain_evidence_id",
]