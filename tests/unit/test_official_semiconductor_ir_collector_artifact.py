from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_cycle import official_semiconductor_ir_collector_cli as collector_cli
from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    DEFAULT_IR_DOCUMENT_REGISTRY,
    load_official_ir_document_registry,
    parse_samsung_2026q2,
)
from alpha_cycle.intelligence.semiconductor_baseline_reconciliation_decision_evidence import (
    load_semiconductor_baseline_reconciliation_decision_evidence,
)
from alpha_cycle.intelligence.semiconductor_forward_input_decision_evidence import (
    load_semiconductor_forward_input_decision_evidence,
)
from alpha_cycle.semiconductor_baseline_reconciliation_cli import (
    capture_semiconductor_baseline_reconciliation,
)
from alpha_cycle.semiconductor_forward_input_cli import capture_forward_input_evidence

EVALUATION = date(2026, 8, 14)
DOCUMENT_ID = "samsung_005930_2026q2_earnings"
SOURCE_BYTES = b"%PDF-synthetic-official-samsung-2q26"


def _pages() -> tuple[str, ...]:
    pages = [""] * 16
    pages[0] = "Samsung Electronics 2Q 2026 Earnings Call"
    pages[6] = "Memory outlook: Scaled up HBM4 sales and robust AI/server memory demand."
    pages[7] = (
        "S.LSI outlook: drive next-generation flagship SoC sales and custom SoC demand. "
        "Foundry outlook: Higher utilization, stronger advanced node demand. "
        "2nm Gen 2 mobile ramp-up and 4nm LPU/Base-Die ramps."
    )
    pages[8] = (
        "SDC outlook: address new model demand in premium products; pursue revenue growth "
        "by timely mass production of 8.6G IT OLED line."
    )
    pages[9] = (
        "MX outlook: drive smartphone market-share growth through flagship-centric sales "
        "acceleration; enhance premium mix; pursue efficiency initiatives to mitigate impact "
        "of rising costs."
    )
    pages[10] = (
        "VD outlook: capture seasonal demand through strengthened channel partnerships. "
        "DA outlook: expand sales of AI-products. Harman outlook: address demand in "
        "high-growth auto segments including central compute unit."
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


def _collect(tmp_path: Path, monkeypatch) -> dict[str, object]:
    spec = load_official_ir_document_registry(DEFAULT_IR_DOCUMENT_REGISTRY)[DOCUMENT_ID]
    parsed = parse_samsung_2026q2(spec, SOURCE_BYTES, _pages())
    monkeypatch.setattr(
        collector_cli,
        "_source_bytes",
        lambda *_args, **_kwargs: SOURCE_BYTES,
    )
    monkeypatch.setattr(
        collector_cli,
        "parse_official_ir_document",
        lambda *_args, **_kwargs: parsed,
    )
    return collector_cli.capture_official_ir_document(
        DOCUMENT_ID,
        evaluation_date=EVALUATION,
        output=tmp_path / "official-ir",
    )


def test_official_ir_artifact_archives_source_and_emits_downstream_packs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _collect(tmp_path, monkeypatch)
    source_path = Path(str(result["source_document_path"]))
    assert source_path.read_bytes() == SOURCE_BYTES
    baseline_pack = json.loads(
        Path(str(result["baseline_fact_pack_path"])).read_text(encoding="utf-8")
    )
    forward_pack = json.loads(
        Path(str(result["forward_input_claim_pack_path"])).read_text(encoding="utf-8")
    )
    assert len(baseline_pack["facts"]) == 7
    assert len(forward_pack["claims"]) == 10
    assert all(row["source_document_path"] == str(source_path) for row in baseline_pack["facts"])
    assert all(row["source_document_path"] == str(source_path) for row in forward_pack["claims"])


def test_collector_baseline_pack_certifies_only_directly_disclosed_segment_bridges(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _collect(tmp_path, monkeypatch)
    raw = json.loads(Path(str(result["baseline_fact_pack_path"])).read_text(encoding="utf-8"))
    output = tmp_path / "baseline"
    captured = capture_semiconductor_baseline_reconciliation(
        raw["facts"],
        evaluation_date=EVALUATION,
        output=output,
    )
    evidence = load_semiconductor_baseline_reconciliation_decision_evidence(
        output / "latest_semiconductor_baseline_reconciliation.json",
        evaluation_date=EVALUATION,
    )
    bridges = evidence.evidence.bridge_coverage
    for block in ("dx", "sdc", "harman"):
        row = bridges.loc[
            bridges["ticker"].eq("005930") & bridges["block_id"].eq(block)
        ].iloc[0]
        assert bool(row["baseline_bridge_certified"]) is True
    memory = bridges.loc[
        bridges["ticker"].eq("005930") & bridges["block_id"].eq("ds_memory")
    ].iloc[0]
    assert bool(memory["baseline_bridge_certified"]) is False
    assert "operating_income" in str(memory["missing_outputs_json"])
    assert captured["residual_derivation_enabled"] is False


def test_collector_forward_pack_is_source_byte_bound_and_non_numeric(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _collect(tmp_path, monkeypatch)
    raw = json.loads(Path(str(result["forward_input_claim_pack_path"])).read_text(encoding="utf-8"))
    claim_pairs = {
        (str(row["block_id"]), str(row["metric_id"])) for row in raw["claims"]
    }
    assert ("dx", "component_cost") in claim_pairs
    assert ("sdc", "oled_panel_volume") in claim_pairs
    assert ("harman", "auto_end_demand") in claim_pairs
    assert ("ds_memory", "dram_asp_change") not in claim_pairs
    assert all(row["evidence_kind"] == "qualitative" for row in raw["claims"])
    assert all(row["numeric_value"] is None for row in raw["claims"])

    output = tmp_path / "forward"
    capture_forward_input_evidence(
        raw["claims"],
        evaluation_date=EVALUATION,
        output=output,
    )
    evidence = load_semiconductor_forward_input_decision_evidence(
        output / "latest_semiconductor_forward_input_evidence.json",
        evaluation_date=EVALUATION,
    )
    samsung = evidence.issuer_coverage.loc[evidence.issuer_coverage["ticker"].eq("005930")].iloc[0]
    assert int(samsung["numeric_input_ready_block_count"]) == 0
    assert bool(samsung["all_numeric_inputs_covered"]) is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False
