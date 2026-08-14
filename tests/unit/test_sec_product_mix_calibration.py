from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import alpha_cycle.intelligence.sec_product_mix_calibration as calibration_module
from alpha_cycle.intelligence.sec_product_mix_calibration import (
    build_sec_product_mix_calibration_evidence,
    capture_sec_product_mix_calibration,
    discover_sec_product_mix_filing,
    load_sec_product_mix_calibration_evidence,
    load_sec_product_mix_registry,
    parse_sec_product_mix_html,
)

DOCUMENT_ID = "skhynix_000660_2026q1_sec_424b4_product_mix"
OBSERVED_DATE = date(2026, 8, 15)


def _spec():
    return load_sec_product_mix_registry()[DOCUMENT_ID]


def _submissions() -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": [
                        "0001193125-26-321989",
                        "0001193125-26-299963",
                    ],
                    "filingDate": ["2026-07-29", "2026-07-10"],
                    "form": ["6-K", "424B4"],
                    "primaryDocument": ["d115239d6k.htm", "d32785d424b4.htm"],
                }
            }
        }
    ).encode("utf-8")


def _filing_html() -> bytes:
    return b"""<!doctype html><html><body>
    <p>The following table presents a breakdown of our revenue by principal product category
    and changes therein for the first quarter of 2026 and the first quarter of 2025.</p>
    <table>
      <tr><td>DRAM</td><td>W</td><td>40,659</td><td>14,037</td></tr>
      <tr><td>NAND flash</td><td>11,574</td><td>3,229</td></tr>
      <tr><td>Other products</td><td>(1)</td><td>343</td><td>373</td></tr>
      <tr><td>Total revenue</td><td>W</td><td>52,576</td><td>17,639</td></tr>
    </table>
    <p>Our revenue increased by 198.1% in the first quarter of 2026.</p>
    <p>The following table sets forth our revenue by principal product category and the
    related percentage data for the periods indicated.</p>
    <table>
      <tr><td>DRAM</td><td>W</td><td>40,659</td><td>77.3</td><td>%</td>
          <td>W</td><td>14,037</td><td>79.6</td><td>%</td></tr>
      <tr><td>NAND Flash</td><td>11,574</td><td>22.0</td><td>%</td>
          <td>3,229</td><td>18.3</td><td>%</td></tr>
      <tr><td>Other Products</td><td>343</td><td>0.7</td><td>%</td>
          <td>373</td><td>2.1</td><td>%</td></tr>
      <tr><td>Total</td><td>W</td><td>52,576</td><td>100.0</td><td>%</td></tr>
    </table>
    <p>DRAMs are a type of random access memory semiconductor.</p>
    </body></html>"""


def test_registry_pins_final_official_424b4_and_keeps_it_historical_only() -> None:
    spec = _spec()
    assert spec.ticker == "000660"
    assert spec.form == "424B4"
    assert spec.filing_date == date(2026, 7, 10)
    assert spec.expected_accession_number == "0001193125-26-299963"
    assert spec.expected_primary_document == "d32785d424b4.htm"
    assert spec.historical_calibration_only is True
    assert spec.current_baseline_eligible is False
    assert spec.q2_allocation_eligible is False
    assert any("related percentage data" in item for item in spec.required_identity_anchors)
    assert all("Sales of NAND" not in item for item in spec.required_identity_anchors)


def test_discovery_requires_exact_pinned_sec_filing() -> None:
    discover_sec_product_mix_filing(_spec(), _submissions())
    payload = json.loads(_submissions())
    payload["filings"]["recent"]["primaryDocument"][1] = "wrong.htm"
    with pytest.raises(ValueError, match="resolve exactly once"):
        discover_sec_product_mix_filing(_spec(), json.dumps(payload).encode("utf-8"))


def test_parser_reads_direct_product_revenue_and_reported_share_table() -> None:
    metrics = parse_sec_product_mix_html(_spec(), _filing_html())
    assert metrics.unit == "KRW_billion"
    assert metrics.total_revenue == 52_576
    assert metrics.dram_revenue == 40_659
    assert metrics.nand_revenue == 11_574
    assert metrics.other_products_revenue == 343
    assert metrics.dram_revenue + metrics.nand_revenue + metrics.other_products_revenue == (
        metrics.total_revenue
    )
    assert metrics.dram_share_percent == pytest.approx(77.3)
    assert metrics.nand_share_percent == pytest.approx(22.0)


def test_direct_share_method_is_calibrated_but_share_only_company_bridge_is_forbidden() -> None:
    evidence = build_sec_product_mix_calibration_evidence(
        _spec(),
        observed_date=OBSERVED_DATE,
        submissions_bytes=_submissions(),
        filing_bytes=_filing_html(),
    )
    assert evidence.direct_product_table_reconciled is True
    assert evidence.direct_share_method_calibrated is True
    assert evidence.dram_share_method_relative_error < 0.001
    assert evidence.nand_share_method_relative_error < 0.001
    assert evidence.other_products_revenue_directly_disclosed is True
    assert evidence.share_only_company_reconciliation_eligible is False
    assert evidence.historical_calibration_only is True
    assert evidence.current_baseline_eligible is False
    assert evidence.q2_allocation_eligible is False
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False
    assert len(evidence.calibration_evidence_id) == 64


def test_parser_rejects_table_or_share_drift() -> None:
    with pytest.raises(ValueError, match="direct revenue table does not reconcile"):
        parse_sec_product_mix_html(
            _spec(),
            _filing_html().replace(b">343<", b">999<", 1),
        )
    with pytest.raises(ValueError, match="DRAM share is inconsistent"):
        parse_sec_product_mix_html(
            _spec(),
            _filing_html().replace(b">77.3<", b">70.0<", 1),
        )


def test_capture_and_loader_reparse_archived_official_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        assert "@" in user_agent
        assert timeout_seconds > 0
        return _submissions() if "submissions" in url else _filing_html()

    monkeypatch.setattr(calibration_module, "download_sec_bytes", fake_download)
    output = tmp_path / "sec-calibration"
    captured = capture_sec_product_mix_calibration(
        _spec(),
        observed_date=OBSERVED_DATE,
        user_agent="AlphaCycleLab research@example.com",
        output=output,
        captured_at=datetime(2026, 8, 15, 1, 0, tzinfo=UTC),
    )
    pointer = output / "latest_sec_product_mix_calibration.json"
    loaded = load_sec_product_mix_calibration_evidence(
        pointer,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == captured["evidence_id"]
    assert loaded.calibration_evidence_id == captured["calibration_evidence_id"]
    assert loaded.metrics.other_products_revenue == 343

    filing_path = Path(str(captured["filing_path"]))
    filing_path.write_bytes(_filing_html().replace(b">343<", b">999<", 1))
    with pytest.raises(ValueError, match="direct revenue table does not reconcile"):
        load_sec_product_mix_calibration_evidence(
            pointer,
            evaluation_date=OBSERVED_DATE,
        )


def test_capture_accepts_new_korea_date_before_utc_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        del user_agent, timeout_seconds
        return _submissions() if "submissions" in url else _filing_html()

    monkeypatch.setattr(calibration_module, "download_sec_bytes", fake_download)
    result = capture_sec_product_mix_calibration(
        _spec(),
        observed_date=OBSERVED_DATE,
        user_agent="AlphaCycleLab research@example.com",
        output=tmp_path / "kst-boundary",
        captured_at=datetime(2026, 8, 14, 16, 0, tzinfo=UTC),
    )
    assert result["observed_date"] == "2026-08-15"


def test_capture_rejects_before_observed_date_in_korea(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        del user_agent, timeout_seconds
        return _submissions() if "submissions" in url else _filing_html()

    monkeypatch.setattr(calibration_module, "download_sec_bytes", fake_download)
    with pytest.raises(ValueError, match="Asia/Seoul"):
        capture_sec_product_mix_calibration(
            _spec(),
            observed_date=OBSERVED_DATE,
            user_agent="AlphaCycleLab research@example.com",
            output=tmp_path / "too-early",
            captured_at=datetime(2026, 8, 14, 14, 59, tzinfo=UTC),
        )


def test_calibration_cannot_be_backdated_before_current_capture_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(url: str, *, user_agent: str, timeout_seconds: float = 20.0) -> bytes:
        del user_agent, timeout_seconds
        return _submissions() if "submissions" in url else _filing_html()

    monkeypatch.setattr(calibration_module, "download_sec_bytes", fake_download)
    output = tmp_path / "sec-calibration"
    capture_sec_product_mix_calibration(
        _spec(),
        observed_date=OBSERVED_DATE,
        user_agent="AlphaCycleLab research@example.com",
        output=output,
        captured_at=datetime(2026, 8, 15, 1, 0, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="not yet observed"):
        load_sec_product_mix_calibration_evidence(
            output / "latest_sec_product_mix_calibration.json",
            evaluation_date=date(2026, 8, 14),
        )
