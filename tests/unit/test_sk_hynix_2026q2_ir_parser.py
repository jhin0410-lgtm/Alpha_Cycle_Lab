from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    OfficialIrDocumentSpec,
    ParsedOfficialIrDocument,
    load_official_ir_document_registry,
)
from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY,
    validate_forward_input_claim,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)
from alpha_cycle.intelligence.sk_hynix_2026q2_ir_parser import parse_sk_hynix_2026q2

EVALUATION_DATE = date(2026, 7, 29)


def _spec() -> OfficialIrDocumentSpec:
    return OfficialIrDocumentSpec(
        document_id="synthetic_sk_hynix_000660_2026q2_earnings",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="sk_hynix_ir",
        document_role="earnings_presentation",
        content_type="pdf",
        source_url="https://www.skhynix.com/ir/synthetic-2q26.pdf",
        source_published_date=EVALUATION_DATE,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        parser_id="sk_hynix_earnings_presentation_2026q2_v1",
        expected_page_count=19,
        required_identity_anchors=(
            "2026.07.29 | Investor Relations",
            "FY2026",
            "Review of the FY2026 Q2 financial results",
        ),
    )


def _pages() -> tuple[str, ...]:
    pages = [""] * 19
    pages[0] = "2026.07.29 | Investor Relations FY2026 Earnings"
    pages[1] = "Review of the FY2026 Q2 financial results"
    pages[8] = """
    DRAM Q3 B/G : Approx. 10% increase QoQ
    NAND Q3 B/G : Low-single% increase QoQ (including Solidigm)
    Active response centered on SV products
    """
    pages[9] = """
    Began HBM4 shipment in Q2
    Full ramp up planned in 2H
    """
    return tuple(pages)


def _claims_by_metric() -> tuple[ParsedOfficialIrDocument, dict[str, dict[str, object]]]:
    parsed = parse_sk_hynix_2026q2(_spec(), b"%PDF-synthetic", _pages())
    claims = {str(row["metric_id"]): row for row in parsed.forward_input_claims}
    return parsed, claims


def test_candidate_parser_remains_dormant_until_official_document_is_registered() -> None:
    specs = load_official_ir_document_registry(DEFAULT_IR_DOCUMENT_REGISTRY)

    assert all(spec.ticker != "000660" for spec in specs.values())


def test_sk_hynix_parser_is_forward_only_and_emits_only_supported_metrics() -> None:
    parsed, claims = _claims_by_metric()

    assert parsed.baseline_facts == ()
    assert set(claims) == {
        "dram_bit_shipment_growth",
        "nand_bit_shipment_growth",
        "dram_product_mix",
        "hbm_generation_mix",
    }
    assert not {
        "dram_asp_change",
        "nand_asp_change",
        "hbm_volume_growth",
        "hbm_capacity",
        "hbm_yield",
        "customer_qualification",
    } & set(claims)
    assert parsed.numeric_forecast_enabled is False
    assert parsed.decision_score_enabled is False


def test_sk_hynix_dram_q3_bit_growth_is_direct_numeric_guidance() -> None:
    _, claims = _claims_by_metric()
    claim = claims["dram_bit_shipment_growth"]

    assert claim["evidence_kind"] == "numeric"
    assert claim["numeric_value"] == 10.0
    assert claim["unit"] == "percent_qoq"
    assert claim["period_start"] == "2026-07-01"
    assert claim["period_end"] == "2026-09-30"


def test_sk_hynix_nand_low_single_guidance_is_not_given_false_numeric_precision() -> None:
    _, claims = _claims_by_metric()
    claim = claims["nand_bit_shipment_growth"]

    assert claim["evidence_kind"] == "qualitative"
    assert claim["numeric_value"] is None
    assert claim["unit"] is None
    assert "low-single" in str(claim["statement"]).casefold()


def test_sk_hynix_hbm_and_product_mix_claims_remain_qualitative() -> None:
    _, claims = _claims_by_metric()

    for metric in ("dram_product_mix", "hbm_generation_mix"):
        claim = claims[metric]
        assert claim["evidence_kind"] == "qualitative"
        assert claim["numeric_value"] is None
    assert "SV products" in str(claims["dram_product_mix"]["statement"])
    assert claims["hbm_generation_mix"]["period_end"] == "2026-12-31"


def test_sk_hynix_parser_claims_validate_against_existing_forward_input_contract() -> None:
    parsed, _ = _claims_by_metric()
    registry = load_structural_source_registry(DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY)
    validated = [
        validate_forward_input_claim(dict(raw), registry, evaluation_date=EVALUATION_DATE)
        for raw in parsed.forward_input_claims
    ]
    eligible = {claim.metric_id: claim.numeric_model_input_eligible for claim in validated}

    assert eligible["dram_bit_shipment_growth"] is True
    assert eligible["nand_bit_shipment_growth"] is False
    assert eligible["dram_product_mix"] is False
    assert eligible["hbm_generation_mix"] is False


def test_sk_hynix_parser_page_count_identity_and_guidance_drift_fail_closed() -> None:
    with pytest.raises(ValueError, match="page count changed"):
        parse_sk_hynix_2026q2(_spec(), b"%PDF-synthetic", _pages()[:-1])

    pages = list(_pages())
    pages[0] = "wrong document"
    with pytest.raises(ValueError, match="identity anchor is missing"):
        parse_sk_hynix_2026q2(_spec(), b"%PDF-synthetic", tuple(pages))

    pages = list(_pages())
    pages[8] = pages[8].replace("Approx. 10% increase QoQ", "changed guidance")
    with pytest.raises(ValueError, match="DRAM Q3 B/G anchor is missing"):
        parse_sk_hynix_2026q2(_spec(), b"%PDF-synthetic", tuple(pages))


def test_sk_hynix_parser_rejects_wrong_issuer_or_parser_identity() -> None:
    wrong_parser = replace(_spec(), parser_id="unknown_parser")
    with pytest.raises(ValueError, match="wrong parser_id"):
        parse_sk_hynix_2026q2(wrong_parser, b"%PDF-synthetic", _pages())

    wrong_ticker = replace(_spec(), ticker="005930")
    with pytest.raises(ValueError, match="wrong issuer/source identity"):
        parse_sk_hynix_2026q2(wrong_ticker, b"%PDF-synthetic", _pages())
