from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.semiconductor_forward_input_evidence import (
    build_semiconductor_forward_input_evidence,
)
from alpha_cycle.intelligence.semiconductor_historical_official_ir import (
    DEFAULT_HISTORICAL_IR_REGISTRY,
    extract_visible_html_text,
    load_historical_official_ir_registry,
    parse_skhynix_2026q1_newsroom,
)
from alpha_cycle.semiconductor_historical_official_ir_cli import (
    capture_historical_official_ir,
)


def _html() -> bytes:
    return b"""<!doctype html><html><head><style>hidden</style><script>fake anchor</script></head>
    <body>
    <h1>SK hynix Announces 1Q26 Financial Results</h1>
    <p>Reports revenue of 52.5763 trillion won, operating profit of 37.6103 trillion won,
    net profit of 40.3459 trillion won.</p>
    <p>The company announced today that it has recorded 52.5763 trillion won in revenue,
    37.6103 trillion won in operating profit and 40.3459 trillion won in net profit.</p>
    <p>High-value-added products, including HBM, high-capacity server DRAM modules, and eSSDs.</p>
    <p>The company forecasted that favorable pricing conditions will continue for both DRAM
    and NAND flash.</p>
    <p>Regarding HBM, capabilities encompass performance, yield, quality, and supply stability.</p>
    <p>Customer demand exceeds supply capacity.</p>
    <p>For NAND, leveraging synergies with Solidigm strengthens AI storage competitiveness.</p>
    </body></html>"""


def test_historical_registry_is_separate_and_not_live_refresh_eligible() -> None:
    specs = load_historical_official_ir_registry(DEFAULT_HISTORICAL_IR_REGISTRY)
    assert set(specs) == {"skhynix_000660_2026q1_newsroom"}
    spec = specs["skhynix_000660_2026q1_newsroom"]
    assert spec.ticker == "000660"
    assert spec.source_id == "sk_hynix_ir"
    assert spec.current_refresh_eligible is False


def test_visible_html_parser_ignores_script_and_style_text() -> None:
    text = extract_visible_html_text(_html())
    assert "SK hynix Announces 1Q26 Financial Results" in text
    assert "fake anchor" not in text
    assert "hidden" not in text


def test_skhynix_1q26_historical_parser_preserves_company_facts_and_expired_claims() -> None:
    spec = load_historical_official_ir_registry(DEFAULT_HISTORICAL_IR_REGISTRY)[
        "skhynix_000660_2026q1_newsroom"
    ]
    parsed = parse_skhynix_2026q1_newsroom(spec, _html())
    facts = {item.metric_id: item.value for item in parsed.company_facts}
    assert facts == {
        "revenue": 52.5763,
        "operating_income": 37.6103,
        "net_income": 40.3459,
    }
    pairs = {(item.block_id, item.metric_id) for item in parsed.forward_claims}
    assert pairs == {
        ("dram_total", "dram_asp_change"),
        ("dram_total", "dram_product_mix"),
        ("hbm_mix_overlay", "hbm_yield"),
        ("hbm_mix_overlay", "hbm_capacity"),
        ("nand_and_solutions", "nand_asp_change"),
        ("nand_and_solutions", "enterprise_ssd_mix"),
    }
    assert all(item.period_end == date(2026, 6, 30) for item in parsed.forward_claims)
    assert parsed.historical_vintage_certified is False
    assert parsed.point_in_time_backtest_eligible is False
    assert parsed.current_forward_coverage_eligible is False


def test_historical_capture_never_promotes_claims_to_current_august_coverage(tmp_path: Path) -> None:
    output = tmp_path / "history"
    pointer = capture_historical_official_ir(
        "skhynix_000660_2026q1_newsroom",
        output=output,
        captured_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        source_bytes=_html(),
    )
    manifest = json.loads(Path(str(pointer["manifest_path"])).read_text(encoding="utf-8"))
    assert manifest["historical_vintage_certified"] is False
    assert manifest["point_in_time_backtest_eligible"] is False
    assert manifest["current_forward_coverage_eligible"] is False

    pack = json.loads(
        Path(str(pointer["historical_forward_claims_path"])).read_text(encoding="utf-8")
    )
    evidence = build_semiconductor_forward_input_evidence(
        pack["claims"],
        evaluation_date=date(2026, 8, 14),
    )
    hynix = evidence.issuer_coverage.loc[evidence.issuer_coverage["ticker"].eq("000660")].iloc[0]
    assert int(hynix["expired_forward_claim_count"]) == 6
    assert int(hynix["descriptive_ready_block_count"]) == 0
    assert bool(hynix["all_descriptive_inputs_covered"]) is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False
