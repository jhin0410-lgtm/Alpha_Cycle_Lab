from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import zipfile
from dataclasses import replace
from datetime import date

import pytest

import alpha_cycle.intelligence.sk_hynix_opendart_pre2023_certified_replay as replay
import alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch as dispatch
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_certified_product_revenue_registry import (
    CertifiedPre2023ProductRevenue,
)
from alpha_cycle.providers.opendart_documents import _safe_member_name


def _zip(member: str, body: bytes, *, extra_member: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, body)
        if extra_member is not None:
            archive.writestr(extra_member, b"extra")
    return output.getvalue()


def _spec() -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id="test-2021q1",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact="test report",
        discovery_begin_date=date(2021, 4, 1),
        discovery_end_date=date(2021, 5, 31),
        period_start=date(2021, 1, 1),
        period_end=date(2021, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("SK hynix",),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND",),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("합계",),
        },
    )


def _legacy_table() -> bytes:
    return """
    <html><body>
      <p>(단위: 백만원)</p>
      <table>
        <tr><th>구분</th><th>당분기</th><th>전분기</th></tr>
        <tr><td>DRAM</td><td>60</td><td>50</td></tr>
        <tr><td>NAND</td><td>20</td><td>18</td></tr>
        <tr><td>기타</td><td>4</td><td>3</td></tr>
        <tr><td>합계</td><td>84</td><td>71</td></tr>
      </table>
    </body></html>
    """.encode()


def _anchor(archive_bytes: bytes) -> CertifiedPre2023ProductRevenue:
    receipt = "20210517000667"
    return CertifiedPre2023ProductRevenue(
        period_id="2021Q1",
        rcept_no=receipt,
        source_archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        member_name=f"{receipt}.xml",
        table_index=0,
        direct_quarter_semantics="direct_quarter_current_period",
        direct_quarter_column_index=1,
        dram_revenue_million_krw=60,
        nand_revenue_million_krw=20,
        other_revenue_million_krw=4,
        total_revenue_million_krw=84,
        company_revenue_krw=84_000_000,
        product_sum_reconciled=True,
        company_revenue_reconciled=True,
        direct_product_revenue_certified=True,
    )


def _raise_current_parser_error(*_args: object, **_kwargs: object) -> None:
    raise ValueError("current parser rejected historical contract")


def _unexpected_fallback(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("unanchored historical fallback must not run")


def test_expansion_cli_imports_from_clean_interpreter() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import alpha_cycle.sk_hynix_company_gp_ex_ante_pit_panel_expansion_cli",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_safe_member_name_allows_only_exact_expected_root_receipt() -> None:
    receipt = "20160516001896"
    assert _safe_member_name(f"/{receipt}.xml", expected_receipt=receipt) == f"{receipt}.xml"

    with pytest.raises(ValueError, match="unsafe member path"):
        _safe_member_name("/20160816001683.xml", expected_receipt=receipt)
    with pytest.raises(ValueError, match="unsafe member path"):
        _safe_member_name("/etc/passwd", expected_receipt=receipt)
    with pytest.raises(ValueError, match="unsafe member path"):
        _safe_member_name("/../20160516001896.xml", expected_receipt=receipt)


def test_parser_only_legacy_root_receipt_view_preserves_payload() -> None:
    receipt = "20160516001896"
    payload = b"<html><body>legacy filing</body></html>"
    raw = _zip(f"/{receipt}.xml", payload)

    parse_view = dispatch._legacy_root_receipt_archive_parse_view(raw)

    assert parse_view != raw
    with zipfile.ZipFile(io.BytesIO(parse_view)) as archive:
        assert archive.namelist() == [f"{receipt}.xml"]
        assert archive.read(f"{receipt}.xml") == payload


def test_parser_only_legacy_root_receipt_view_does_not_sanitize_broadly() -> None:
    payload = b"legacy"
    multiple = _zip("/20160516001896.xml", payload, extra_member="other.xml")
    arbitrary_absolute = _zip("/not-a-receipt.xml", payload)
    traversal = _zip("../20160516001896.xml", payload)

    assert dispatch._legacy_root_receipt_archive_parse_view(multiple) == multiple
    assert (
        dispatch._legacy_root_receipt_archive_parse_view(arbitrary_absolute)
        == arbitrary_absolute
    )
    assert dispatch._legacy_root_receipt_archive_parse_view(traversal) == traversal


def test_parser_only_legacy_root_receipt_view_enforces_uncompressed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = "20160516001896"
    raw = _zip(f"/{receipt}.xml", b"123456789")
    monkeypatch.setattr(dispatch, "MAX_DOCUMENT_UNCOMPRESSED_BYTES", 8)

    with pytest.raises(ValueError, match="uncompressed-size limit"):
        dispatch._legacy_root_receipt_archive_parse_view(raw)


def test_exact_pre2023_archive_replays_registered_table(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = "20210517000667"
    raw = _zip(f"{receipt}.xml", _legacy_table())
    anchor = _anchor(raw)
    monkeypatch.setattr(replay, "_anchor", lambda _spec_value: anchor)

    metrics = replay.parse_pre2023_certified_product_revenue_archive(_spec(), raw)

    assert metrics.dram_total == 60.0
    assert metrics.nand_and_solutions == 20.0
    assert metrics.other_products_services == 4.0
    assert metrics.reported_company_revenue == 84.0
    assert metrics.reconciliation_delta == 0.0


def test_exact_pre2023_archive_fails_on_byte_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = "20210517000667"
    raw = _zip(f"{receipt}.xml", _legacy_table())
    anchor = _anchor(raw)
    monkeypatch.setattr(replay, "_anchor", lambda _spec_value: anchor)
    changed = _zip(f"{receipt}.xml", _legacy_table() + b"\n")

    with pytest.raises(ValueError, match="archive SHA-256"):
        replay.parse_pre2023_certified_product_revenue_archive(_spec(), changed)


def test_dispatch_fails_closed_on_certified_archive_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = "20210517000667"
    raw = _zip(f"{receipt}.xml", _legacy_table())
    anchor = _anchor(raw)
    changed = _zip(f"{receipt}.xml", _legacy_table() + b"\n")
    monkeypatch.setattr(replay, "_anchor", lambda _spec_value: anchor)
    monkeypatch.setattr(dispatch, "_current_archive_parser", _raise_current_parser_error)
    monkeypatch.setattr(
        dispatch,
        "parse_historical_product_revenue_archive_fallback",
        _unexpected_fallback,
    )

    with pytest.raises(ValueError, match="archive SHA-256"):
        dispatch.parse_periodic_product_revenue_archive(_spec(), changed)


def test_exact_pre2023_text_is_secondary_exact_value_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = "20210517000667"
    raw = _zip(f"{receipt}.xml", _legacy_table())
    anchor = _anchor(raw)
    monkeypatch.setattr(replay, "_anchor", lambda _spec_value: anchor)

    metrics = replay.parse_pre2023_certified_product_revenue_text(
        _spec(),
        "DRAM 60 / NAND 20 / 기타 4 / 합계 84",
    )
    assert metrics.reported_company_revenue == 84.0

    with pytest.raises(ValueError, match="exact anchored amounts"):
        replay.parse_pre2023_certified_product_revenue_text(
            _spec(),
            "DRAM 60 / NAND 20 / 기타 5 / 합계 85",
        )


def test_dispatch_fails_closed_on_certified_text_witness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = "20210517000667"
    raw = _zip(f"{receipt}.xml", _legacy_table())
    anchor = _anchor(raw)
    monkeypatch.setattr(replay, "_anchor", lambda _spec_value: anchor)
    monkeypatch.setattr(dispatch, "_current_text_parser", _raise_current_parser_error)
    monkeypatch.setattr(
        dispatch,
        "parse_historical_product_revenue_text_prioritized",
        _unexpected_fallback,
    )

    with pytest.raises(ValueError, match="exact anchored amounts"):
        dispatch.parse_periodic_product_revenue_text(
            _spec(),
            "DRAM 60 / NAND 20 / 기타 5 / 합계 85",
        )


def test_unsupported_period_rejects_before_registry_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_spec = replace(
        _spec(),
        document_id="test-2016q1",
        discovery_begin_date=date(2016, 4, 1),
        discovery_end_date=date(2016, 5, 31),
        period_start=date(2016, 1, 1),
        period_end=date(2016, 3, 31),
    )

    def _unexpected_registry_load() -> None:
        raise AssertionError("unsupported periods must not load the certified registry")

    monkeypatch.setattr(
        replay,
        "load_certified_pre2023_product_revenue_registry",
        _unexpected_registry_load,
    )

    with pytest.raises(ValueError, match="limited to 2021Q1-2022Q3"):
        replay.parse_pre2023_certified_product_revenue_text(legacy_spec, "legacy")
