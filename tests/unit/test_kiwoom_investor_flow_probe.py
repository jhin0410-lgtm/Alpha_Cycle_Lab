"""Tests for the read-only Kiwoom OPT10059 investor-flow probe."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

BRIDGE = Path("bridge/kiwoom_openapi_plus")
FLOW_PATH = BRIDGE / "investor_flow_export.py"


def _load_flow() -> ModuleType:
    bridge_text = str(BRIDGE.resolve())
    if bridge_text not in sys.path:
        sys.path.insert(0, bridge_text)
    spec = importlib.util.spec_from_file_location(
        "kiwoom_investor_flow_export_test",
        FLOW_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_investor_flow_request_is_net_buy_quantity_in_single_shares() -> None:
    flow = _load_flow()
    exporter = object.__new__(flow.KiwoomInvestorFlowExporter)
    captured: dict[str, Any] = {}

    def fake_request(**kwargs: Any) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "tr_code": flow.TR_CODE,
            "screen_no": "9300",
            "previous_next": "2",
            "rows": [
                {
                    "date": "20260807",
                    "current_price": "-120000",
                    "change": "+1000",
                    "change_percent": "0.84",
                    "cumulative_volume": "10,000,000",
                    "cumulative_value": "1,200,000",
                    "individual": "-120000",
                    "foreign": "+80000",
                    "institution": "+40000",
                    "financial_investment": "+10000",
                    "insurance": "0",
                    "investment_trust": "+5000",
                    "other_finance": "0",
                    "bank": "0",
                    "pension": "+25000",
                    "private_fund": "0",
                    "state": "0",
                    "other_corporation": "0",
                    "domestic_foreign": "0",
                }
            ],
        }

    exporter._request = fake_request
    records = exporter.investor_flows(
        "000660",
        screen_no="9300",
        reference_date="20260808",
        limit=60,
    )

    assert captured["tr_code"] == "opt10059"
    assert captured["inputs"] == (
        ("일자", "20260808"),
        ("종목코드", "000660"),
        ("금액수량구분", "2"),
        ("매매구분", "0"),
        ("단위구분", "1"),
    )
    assert len(records) == 1
    record = records[0]
    assert record.individual_net_buy_shares == -120_000
    assert record.foreign_net_buy_shares == 80_000
    assert record.institution_net_buy_shares == 40_000
    assert record.pension_net_buy_shares == 25_000
    assert record.previous_next == "2"


def test_investor_flow_export_is_unscored_and_pointer_is_ascii_safe(
    tmp_path: Path,
) -> None:
    flow = _load_flow()
    record = flow.InvestorFlowRecord(
        ticker="005930",
        date="20260807",
        current_price=100000,
        change=1000,
        change_percent=1.0,
        cumulative_volume=1000000,
        cumulative_value=100000,
        individual_net_buy_shares=-100,
        foreign_net_buy_shares=60,
        institution_net_buy_shares=40,
        financial_investment_net_buy_shares=10,
        insurance_net_buy_shares=0,
        investment_trust_net_buy_shares=5,
        other_finance_net_buy_shares=0,
        bank_net_buy_shares=0,
        pension_net_buy_shares=25,
        private_fund_net_buy_shares=0,
        state_net_buy_shares=0,
        other_corporation_net_buy_shares=0,
        domestic_foreign_net_buy_shares=0,
        raw_json="{}",
        request_name="investor_005930",
        tr_code="opt10059",
        screen_no="9300",
        previous_next="2",
    )
    exporter = SimpleNamespace(
        provider_messages=(),
    )
    output_root = tmp_path / "쿠쿠" / "flow"

    manifest, directory = flow.write_export(
        output_root=output_root,
        reference_date="20260808",
        symbols=("005930",),
        limit=60,
        records=[record],
        exporter=exporter,
    )

    assert manifest.semantic_status == flow.SEMANTIC_STATUS
    assert manifest.decision_score_enabled is False
    assert manifest.account_api_enabled is False
    assert manifest.holdings_api_enabled is False
    assert manifest.balance_api_enabled is False
    assert manifest.order_api_enabled is False
    assert (directory / "investor_flows.csv").is_file()
    pointer = output_root / "latest_investor_flow_export.json"
    raw = pointer.read_bytes()
    text = raw.decode("ascii")
    assert "쿠쿠" not in text
    payload = json.loads(text)
    assert "쿠쿠" in payload["export_directory"]
    assert payload["decision_score_enabled"] is False
