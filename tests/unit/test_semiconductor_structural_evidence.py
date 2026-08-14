from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    build_structural_evidence_bundle,
    load_structural_source_registry,
    validate_structural_claim,
)

REGISTRY = Path("config/semiconductor_structural_sources.yaml")


def test_company_ir_can_support_hbm_claim_but_not_numeric_memory_price() -> None:
    registry = load_structural_source_registry(REGISTRY)
    claim = validate_structural_claim(
        {
            "subject": "005930",
            "dimension": "hbm_demand_mix",
            "source_id": "samsung_ir",
            "source_url": "https://news.samsung.com/global/example-hbm4",
            "source_published_date": "2026-08-01",
            "evidence_kind": "qualitative",
            "statement": "Issuer primary-source statement about HBM demand and product mix.",
            "issuer_specific": True,
        },
        registry,
        evaluation_date=date(2026, 8, 14),
    )
    assert claim.decision_score_enabled is False
    assert claim.dimension == "hbm_demand_mix"
    assert claim.numeric_value is None

    with pytest.raises(ValueError, match="cannot support dimension"):
        validate_structural_claim(
            {
                "subject": "005930",
                "dimension": "memory_numeric_price",
                "source_id": "samsung_ir",
                "source_url": "https://news.samsung.com/global/example-memory-price",
                "source_published_date": "2026-08-01",
                "evidence_kind": "numeric",
                "numeric_value": 12.3,
                "unit": "USD",
                "product_scope": "DRAM example",
                "statement": "A number quoted in company commentary must not become price data.",
            },
            registry,
            evaluation_date=date(2026, 8, 14),
        )


def test_certified_numeric_memory_price_requires_semantics_scope_and_reuse_basis() -> None:
    registry = load_structural_source_registry(REGISTRY)
    base = {
        "subject": "industry",
        "dimension": "memory_numeric_price",
        "source_id": "certified_memory_price",
        "source_url": "https://licensed.example.test/series/dram",
        "source_published_date": "2026-08-14",
        "evidence_kind": "numeric",
        "numeric_value": 2.45,
        "unit": "USD/unit",
        "product_scope": "explicit DRAM product definition",
        "statement": "Certified numeric memory-price observation.",
    }
    with pytest.raises(ValueError, match="certified provider semantics"):
        validate_structural_claim(
            base,
            registry,
            evaluation_date=date(2026, 8, 14),
        )

    claim = validate_structural_claim(
        {
            **base,
            "semantics_certified": True,
            "reuse_basis_documented": True,
        },
        registry,
        evaluation_date=date(2026, 8, 14),
    )
    assert claim.numeric_value == pytest.approx(2.45)
    assert claim.semantics_certified is True
    assert claim.reuse_basis_documented is True


def test_registered_primary_domains_are_enforced() -> None:
    registry = load_structural_source_registry(REGISTRY)
    with pytest.raises(ValueError, match="outside registered domains"):
        validate_structural_claim(
            {
                "subject": "000660",
                "dimension": "hbm_capacity_yield",
                "source_id": "sk_hynix_ir",
                "source_url": "https://random-news.example/hbm",
                "source_published_date": "2026-08-01",
                "evidence_kind": "qualitative",
                "statement": "Secondary article cannot masquerade as issuer IR.",
            },
            registry,
            evaluation_date=date(2026, 8, 14),
        )


def test_bundle_stays_non_scoring_even_with_multiple_primary_sources() -> None:
    registry = load_structural_source_registry(REGISTRY)
    bundle = build_structural_evidence_bundle(
        [
            {
                "subject": "000660",
                "dimension": "hbm_capacity_yield",
                "source_id": "sk_hynix_ir",
                "source_url": "https://news.skhynix.com/example-hbm4e",
                "source_published_date": "2026-06-18",
                "evidence_kind": "qualitative",
                "statement": "Issuer evidence about HBM generation and manufacturing.",
                "issuer_specific": True,
            },
            {
                "subject": "industry",
                "dimension": "export_control",
                "source_id": "us_bis",
                "source_url": "https://www.bis.gov/regulations/ear/740",
                "source_published_date": "2026-08-01",
                "evidence_kind": "qualitative",
                "statement": "Government primary-source HBM export-control rule.",
            },
        ],
        registry,
        evaluation_date=date(2026, 8, 14),
    )
    assert bundle.decision_score_enabled is False
    assert bundle.numeric_memory_price_signal_enabled is False
    assert len(bundle.claims) == 2
