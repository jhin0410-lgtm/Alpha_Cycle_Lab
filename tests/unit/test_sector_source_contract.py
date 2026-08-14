from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sector_source_contract import (
    load_sector_source_registry,
    prohibited_proxy_rules,
    validate_sector_evidence_claim,
)

REGISTRY = Path("config/sector_primary_sources.yaml")
EVALUATION = date(2026, 8, 14)


def test_sector_source_registry_covers_all_deep_verticals_without_generic_collapse() -> None:
    registry = load_sector_source_registry(REGISTRY)
    assert set(registry) == {
        "semiconductor",
        "defense",
        "shipbuilding",
        "power_equipment",
        "nuclear",
        "construction",
        "battery",
        "auto",
        "bio",
        "internet_platform",
        "robotics",
    }
    assert registry["semiconductor"].delegates_to == "config/semiconductor_structural_sources.yaml"
    assert "contract_award" in {
        dimension
        for source in registry["defense"].sources
        for dimension in source.dimensions
    }
    assert "newbuild_price" not in {
        dimension
        for source in registry["shipbuilding"].sources
        for dimension in source.dimensions
    }
    assert "pf_credit_conditions" in {
        dimension
        for source in registry["construction"].sources
        for dimension in source.dimensions
    }
    assert "trial_endpoint" in {
        dimension for source in registry["bio"].sources for dimension in source.dimensions
    }


def test_semiconductor_uses_dedicated_contract_instead_of_generic_sector_claims() -> None:
    registry = load_sector_source_registry(REGISTRY)
    with pytest.raises(ValueError, match="delegates to a dedicated evidence contract"):
        validate_sector_evidence_claim(
            {
                "sector_id": "semiconductor",
                "subject": "000660",
                "source_id": "issuer_ir",
                "dimension": "hbm_demand_mix",
                "source_url": "https://news.skhynix.com/example",
                "source_published_date": "2026-08-01",
                "statement": "Must use the dedicated semiconductor structural contract.",
            },
            registry,
            evaluation_date=EVALUATION,
        )


def test_issuer_ir_requires_explicit_subject_domain_binding() -> None:
    registry = load_sector_source_registry(REGISTRY)
    raw = {
        "sector_id": "defense",
        "subject": "012450",
        "source_id": "issuer_ir",
        "dimension": "backlog",
        "source_url": "https://www.hanwhaaerospace.com/ir/example",
        "source_published_date": "2026-08-01",
        "statement": "Issuer primary-source backlog evidence.",
    }
    with pytest.raises(ValueError, match="explicit domain binding"):
        validate_sector_evidence_claim(raw, registry, evaluation_date=EVALUATION)

    claim = validate_sector_evidence_claim(
        raw,
        registry,
        evaluation_date=EVALUATION,
        issuer_domains={"012450": ("hanwhaaerospace.com",)},
    )
    assert claim.source_role == "issuer_ir"
    assert claim.issuer_specific is True
    assert claim.decision_score_enabled is False


def test_wrong_official_domain_cannot_masquerade_as_sector_primary_source() -> None:
    registry = load_sector_source_registry(REGISTRY)
    with pytest.raises(ValueError, match="outside registered domains"):
        validate_sector_evidence_claim(
            {
                "sector_id": "construction",
                "subject": "industry",
                "source_id": "molit",
                "dimension": "unsold_inventory",
                "source_url": "https://random-news.example/housing",
                "source_published_date": "2026-08-01",
                "statement": "Secondary news cannot masquerade as MOLIT evidence.",
            },
            registry,
            evaluation_date=EVALUATION,
        )


def test_prohibited_generic_proxies_are_explicit_by_sector() -> None:
    rules = prohibited_proxy_rules(load_sector_source_registry(REGISTRY))
    assert "baltic_dry_index_as_shipyard_newbuild_price" in rules["shipbuilding"]
    assert "memorandum_of_understanding_as_firm_order" in rules["nuclear"]
    assert "housing_price_index_as_project_profitability" in rules["construction"]
    assert "press_release_trial_success_without_primary_endpoint_result" in rules["bio"]
