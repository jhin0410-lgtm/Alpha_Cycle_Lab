from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.semiconductor_structural_decision_evidence import (
    build_structural_coverages,
    structural_coverage_frame,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    build_structural_evidence_bundle,
    load_structural_source_registry,
)

REGISTRY = Path("config/semiconductor_structural_sources.yaml")


def _claim(
    *,
    subject: str,
    dimension: str,
    source_id: str,
    source_url: str,
    issuer_specific: bool = False,
) -> dict[str, object]:
    return {
        "subject": subject,
        "dimension": dimension,
        "source_id": source_id,
        "source_url": source_url,
        "source_published_date": "2026-08-01",
        "evidence_kind": "qualitative",
        "statement": f"Primary-source evidence for {dimension}.",
        "issuer_specific": issuer_specific,
    }


def test_cross_source_hbm_and_competition_require_customer_confirmation() -> None:
    registry = load_structural_source_registry(REGISTRY)
    bundle = build_structural_evidence_bundle(
        [
            _claim(
                subject="005930",
                dimension="hbm_demand_mix",
                source_id="samsung_ir",
                source_url="https://news.samsung.com/global/hbm-example",
                issuer_specific=True,
            ),
            _claim(
                subject="005930",
                dimension="competitive_position",
                source_id="samsung_ir",
                source_url="https://news.samsung.com/global/competitive-example",
                issuer_specific=True,
            ),
            _claim(
                subject="005930",
                dimension="qualification",
                source_id="amd_ir",
                source_url="https://ir.amd.com/news-events/press-releases/example",
                issuer_specific=True,
            ),
            _claim(
                subject="industry",
                dimension="export_control",
                source_id="us_bis",
                source_url="https://www.bis.gov/regulations/ear/740",
            ),
            _claim(
                subject="industry",
                dimension="end_demand",
                source_id="micron_ir",
                source_url="https://investors.micron.com/news-releases/example",
            ),
        ],
        registry,
        evaluation_date=date(2026, 8, 14),
    )
    coverages = {item.ticker: item for item in build_structural_coverages(bundle, registry)}

    samsung = coverages["005930"]
    hynix = coverages["000660"]
    assert samsung.hbm_demand_mix_status == "available"
    assert samsung.competitive_position_status == "available"
    assert samsung.end_demand_status == "partial"
    assert samsung.export_control_status == "available"
    assert samsung.decision_score_enabled is False

    assert hynix.hbm_demand_mix_status == "missing"
    assert hynix.competitive_position_status == "missing"
    assert hynix.end_demand_status == "partial"
    assert hynix.export_control_status == "available"

    frame = structural_coverage_frame(
        type("Evidence", (), {"bundle": bundle, "coverages": tuple(coverages.values())})()  # type: ignore[arg-type]
    )
    assert frame["structural_decision_score_enabled"].eq(False).all()
    assert frame["structural_numeric_memory_price_signal_enabled"].eq(False).all()


def test_issuer_only_hbm_claim_stays_partial() -> None:
    registry = load_structural_source_registry(REGISTRY)
    bundle = build_structural_evidence_bundle(
        [
            _claim(
                subject="000660",
                dimension="hbm_demand_mix",
                source_id="sk_hynix_ir",
                source_url="https://news.skhynix.com/hbm-example",
                issuer_specific=True,
            )
        ],
        registry,
        evaluation_date=date(2026, 8, 14),
    )
    coverages = {item.ticker: item for item in build_structural_coverages(bundle, registry)}
    assert coverages["000660"].hbm_demand_mix_status == "partial"
    assert coverages["005930"].hbm_demand_mix_status == "missing"
