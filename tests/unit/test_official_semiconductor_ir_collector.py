from __future__ import annotations

from dataclasses import replace

import pytest

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    load_official_ir_document_registry,
    parse_samsung_2026q2,
)


def _spec():
    return load_official_ir_document_registry(DEFAULT_IR_DOCUMENT_REGISTRY)[
        "samsung_005930_2026q2_earnings"
    ]


def _pages() -> tuple[str, ...]:
    pages = [""] * 16
    pages[0] = "Samsung Electronics 2Q 2026 Earnings Call"
    pages[6] = "Memory outlook: Scaled up HBM4 sales and robust AI/server memory demand."
    pages[7] = (
        "Foundry outlook: Higher utilization, stronger advanced node demand. "
        "2nm Gen 2 mobile ramp-up and 4nm LPU/Base-Die ramps."
    )
    pages[12] = """
    Appendix 2: Results by Business Segment
    Sales
    DX 43.6 52.7 48.0
    DS 27.9 81.7 127.5
    Memory 21.2 74.8 120.8
    SDC 6.4 6.7 7.5
    Harman 3.8 3.8 4.6
    Operating Profit
    DX 3.3 3.0 (0.8)
    DS 0.4 53.7 89.2
    SDC 0.5 0.4 0.7
    Harman 0.5 0.2 0.4
    """
    return tuple(pages)


def test_registry_registers_only_verified_samsung_2q26_document() -> None:
    specs = load_official_ir_document_registry(DEFAULT_IR_DOCUMENT_REGISTRY)
    assert set(specs) == {"samsung_005930_2026q2_earnings"}
    spec = specs["samsung_005930_2026q2_earnings"]
    assert spec.ticker == "005930"
    assert spec.source_id == "samsung_ir"
    assert spec.parser_id == "samsung_earnings_presentation_2026q2_v1"
    assert spec.expected_page_count == 16


def test_samsung_2q26_parser_emits_only_direct_same_scope_accounting_facts() -> None:
    parsed = parse_samsung_2026q2(_spec(), b"%PDF-synthetic", _pages())
    facts = {
        (str(row["scope_id"]), str(row["metric_id"])): float(row["value"])
        for row in parsed.baseline_facts
    }
    assert facts[("dx", "revenue")] == 48.0
    assert facts[("dx", "operating_income")] == -0.8
    assert facts[("ds_memory", "revenue")] == 120.8
    assert ("ds_memory", "operating_income") not in facts
    assert facts[("sdc", "revenue")] == 7.5
    assert facts[("sdc", "operating_income")] == 0.7
    assert facts[("harman", "revenue")] == 4.6
    assert facts[("harman", "operating_income")] == 0.4
    assert parsed.parser_semantics_certified is True
    assert parsed.numeric_forecast_enabled is False
    assert parsed.decision_score_enabled is False


def test_samsung_2q26_parser_emits_bounded_qualitative_forward_claims() -> None:
    parsed = parse_samsung_2026q2(_spec(), b"%PDF-synthetic", _pages())
    claims = {(str(row["block_id"]), str(row["metric_id"])) for row in parsed.forward_input_claims}
    assert claims == {
        ("ds_memory", "hbm_volume_and_mix"),
        ("ds_foundry_system_lsi", "foundry_utilization"),
        ("ds_foundry_system_lsi", "customer_ramp"),
    }
    assert all(row["evidence_kind"] == "qualitative" for row in parsed.forward_input_claims)
    assert all(row["numeric_value"] is None for row in parsed.forward_input_claims)


def test_samsung_parser_drift_fails_closed_instead_of_shifting_values() -> None:
    pages = list(_pages())
    pages[12] = pages[12].replace("SDC 0.5 0.4 0.7", "SDC 0.5 0.4")
    with pytest.raises(ValueError, match="SDC 2Q26 operating income"):
        parse_samsung_2026q2(_spec(), b"%PDF-synthetic", tuple(pages))


def test_samsung_parser_page_count_and_identity_are_pinned() -> None:
    with pytest.raises(ValueError, match="page count changed"):
        parse_samsung_2026q2(_spec(), b"%PDF-synthetic", _pages()[:-1])

    pages = list(_pages())
    pages[0] = "wrong document"
    with pytest.raises(ValueError, match="identity anchor is missing"):
        parse_samsung_2026q2(_spec(), b"%PDF-synthetic", tuple(pages))


def test_wrong_parser_id_is_rejected() -> None:
    bad = replace(_spec(), parser_id="unknown")
    with pytest.raises(ValueError, match="wrong parser_id"):
        parse_samsung_2026q2(bad, b"%PDF-synthetic", _pages())
