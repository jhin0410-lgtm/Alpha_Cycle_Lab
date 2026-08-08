"""Tests for non-scoring Kiwoom investor-flow live diagnostics."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from alpha_cycle.investor_flow_diagnostics_cli import build_report


def _write_fixture(tmp_path: Path) -> Path:
    export_dir = tmp_path / "쿠쿠" / "flow" / "snapshot"
    export_dir.mkdir(parents=True)
    csv_path = export_dir / "investor_flows.csv"
    manifest_path = export_dir / "manifest.json"
    pointer_path = tmp_path / "latest.json"

    fieldnames = [
        "ticker",
        "date",
        "current_price",
        "cumulative_volume",
        "individual_net_buy_shares",
        "foreign_net_buy_shares",
        "institution_net_buy_shares",
        "financial_investment_net_buy_shares",
        "insurance_net_buy_shares",
        "investment_trust_net_buy_shares",
        "other_finance_net_buy_shares",
        "bank_net_buy_shares",
        "pension_net_buy_shares",
        "private_fund_net_buy_shares",
        "state_net_buy_shares",
        "other_corporation_net_buy_shares",
        "domestic_foreign_net_buy_shares",
    ]
    rows: list[dict[str, object]] = []
    for index in range(20):
        institution = -200 - index
        financial = -50
        insurance = -10
        trust = -20
        other_finance = -5
        bank = -5
        pension = -80
        private_fund = -20
        state = institution - (
            financial
            + insurance
            + trust
            + other_finance
            + bank
            + pension
            + private_fund
        )
        foreign = -300 - index
        individual = 450 + index
        domestic_foreign = 0
        other_corporation = -(
            individual + foreign + institution + domestic_foreign
        )
        rows.append(
            {
                "ticker": "005930",
                "date": f"202608{7 - index:02d}" if index < 7 else f"202607{31 - (index - 7):02d}",
                "current_price": str(-(100_000 - index * 1_000)),
                "cumulative_volume": "10000",
                "individual_net_buy_shares": individual,
                "foreign_net_buy_shares": foreign,
                "institution_net_buy_shares": institution,
                "financial_investment_net_buy_shares": financial,
                "insurance_net_buy_shares": insurance,
                "investment_trust_net_buy_shares": trust,
                "other_finance_net_buy_shares": other_finance,
                "bank_net_buy_shares": bank,
                "pension_net_buy_shares": pension,
                "private_fund_net_buy_shares": private_fund,
                "state_net_buy_shares": state,
                "other_corporation_net_buy_shares": other_corporation,
                "domestic_foreign_net_buy_shares": domestic_foreign,
            }
        )

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest_path.write_text(
        json.dumps(
            {
                "amount_quantity_type": "2",
                "trade_type": "0",
                "unit_type": "1",
                "decision_score_enabled": False,
                "account_api_enabled": False,
                "order_api_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    pointer_path.write_text(
        json.dumps(
            {
                "source_scope": "kiwoom_openapi_plus_opt10059_net_buy_quantity",
                "snapshot_id": "fixture",
                "semantic_status": "provider_field_mapping_pending_live_certification",
                "investor_flows_path": str(csv_path),
                "manifest_path": str(manifest_path),
            },
            ensure_ascii=True,
        ),
        encoding="ascii",
    )
    return pointer_path


def test_build_report_normalizes_signed_prices_and_keeps_scoring_disabled(
    tmp_path: Path,
) -> None:
    report = build_report(_write_fixture(tmp_path))

    assert report.request_contract_status == "verified_net_buy_quantity_single_share_unscored"
    assert report.semantics_certified is False
    assert report.decision_score_enabled is False
    assert len(report.tickers) == 1
    diag = report.tickers[0]
    assert diag.date_order_descending is True
    assert diag.positive_normalized_price_rows == 20
    assert diag.exact_market_balance_rows == 20
    assert diag.max_abs_market_balance_residual_shares == 0
    assert diag.exact_institution_breakdown_rows == 20
    assert diag.max_abs_institution_breakdown_residual_shares == 0

    five = next(row for row in report.windows if row.window == 5)
    assert five.latest_price_abs == 100_000
    assert five.oldest_price_abs == 96_000
    assert five.price_return_pct is not None
    assert five.price_return_pct > 0
    assert five.foreign_institution_net_buy_shares is not None
    assert five.foreign_institution_net_buy_shares < 0
    assert five.descriptive_state == "selling_divergence"
    assert five.decision_score_enabled is False


def test_request_contract_fails_closed_on_wrong_unit(tmp_path: Path) -> None:
    pointer = _write_fixture(tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="ascii"))
    manifest_path = Path(pointer_payload["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["unit_type"] = "1000"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_report(pointer)

    assert report.request_contract_status == "contract_mismatch:unit_type"
    assert report.semantics_certified is False
    assert report.decision_score_enabled is False
