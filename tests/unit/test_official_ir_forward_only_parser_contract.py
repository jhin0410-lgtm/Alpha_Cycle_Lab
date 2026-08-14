from datetime import date

import pytest

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    OfficialIrDocumentSpec,
    ParsedOfficialIrDocument,
)


def _spec() -> OfficialIrDocumentSpec:
    return OfficialIrDocumentSpec(
        document_id="synthetic_forward_only_ir",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="sk_hynix_ir",
        document_role="earnings_presentation",
        content_type="pdf",
        source_url="https://www.skhynix.com/ir/synthetic-forward-only.pdf",
        source_published_date=date(2026, 7, 29),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        parser_id="synthetic_forward_only_v1",
        expected_page_count=1,
        required_identity_anchors=("SK hynix",),
    )


def _claim() -> dict[str, object]:
    return {
        "ticker": "000660",
        "block_id": "dram_total",
        "claim_type": "forward_driver",
        "metric_id": "dram_bit_shipment_growth",
        "evidence_kind": "qualitative",
        "statement": "Issuer provided bounded forward shipment guidance.",
    }


def test_parsed_official_ir_may_be_forward_only_when_no_safe_baseline_bridge_exists() -> None:
    parsed = ParsedOfficialIrDocument(
        spec=_spec(),
        source_document_sha256="a" * 64,
        pages=("SK hynix",),
        baseline_facts=(),
        forward_input_claims=(_claim(),),
        parser_semantics_certified=True,
    )

    assert parsed.baseline_facts == ()
    assert len(parsed.forward_input_claims) == 1
    assert parsed.numeric_forecast_enabled is False
    assert parsed.decision_score_enabled is False


def test_parsed_official_ir_still_rejects_evidence_free_parser_output() -> None:
    with pytest.raises(ValueError, match="at least one baseline fact or forward-input claim"):
        ParsedOfficialIrDocument(
            spec=_spec(),
            source_document_sha256="b" * 64,
            pages=("SK hynix",),
            baseline_facts=(),
            forward_input_claims=(),
            parser_semantics_certified=True,
        )
