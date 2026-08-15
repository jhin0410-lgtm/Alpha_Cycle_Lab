from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DiscoveredPeriodicProductRevenue,
    build_periodic_product_revenue_certification,
    discover_periodic_product_revenue,
    load_periodic_product_revenue_registry,
    parse_periodic_product_revenue_text,
)
from alpha_cycle.providers.opendart import CorpCode, DisclosureBatch
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    _parse_document_archive,
)

EVALUATION = date(2026, 8, 14)
DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"
RECEIPT = "20260814001234"


def _spec():
    return load_periodic_product_revenue_registry()[DOCUMENT_ID]


def _text() -> str:
    return "\n".join(
        [
            "반기보고서 (2026.06)",
            "제품별 매출액",
            "당반기",
            "(단위 : 백만원)",
            "구분",
            "3개월",
            "누적",
            "전반기",
            "3개월",
            "누적",
            "DRAM",
            "28,900,000",
            "51,000,000",
            "16,000,000",
            "30,000,000",
            "NAND",
            "10,700,000",
            "19,000,000",
            "7,000,000",
            "13,000,000",
            "기타",
            "400,000",
            "700,000",
            "300,000",
            "500,000",
            "합계",
            "40,000,000",
            "70,700,000",
            "23,300,000",
            "43,500,000",
        ]
    )


def _corp() -> CorpCode:
    return CorpCode(
        corp_code="00164779",
        corp_name="SK하이닉스",
        stock_code="000660",
        modify_date=date(2026, 1, 1),
    )


class _FakeDisclosureClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def resolve_stock_codes(self, symbols):
        assert list(symbols) == ["000660"]
        return {"000660": _corp()}

    def disclosures(self, corp, *, begin_date, end_date):
        assert corp == _corp()
        assert begin_date == date(2026, 8, 10)
        assert end_date == date(2026, 8, 14)
        return DisclosureBatch(self.frame, raw_payload={"pages": []})


def _row(*, receipt: str = RECEIPT, report_name: str | None = None, correction: bool = False):
    return {
        "ticker": "000660",
        "corp_code": "00164779",
        "corp_name": "SK하이닉스",
        "rcept_no": receipt,
        "report_name": report_name or _spec().report_name_exact,
        "receipt_date": date(2026, 8, 14),
        "corp_class": "Y",
        "is_correction": correction,
    }


def _archive(text: str | None = None) -> DisclosureDocumentArchive:
    body = text if text is not None else _text()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", f"<html><body>{body.replace(chr(10), '<br>')}</body></html>")
    raw = buffer.getvalue()
    evidence = _parse_document_archive(
        raw,
        receipt=RECEIPT,
        retrieved_at=datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
    )
    return DisclosureDocumentArchive(evidence=evidence, archive_bytes=raw)


def test_registry_requires_exact_half_year_report_without_receipt_number() -> None:
    spec = _spec()
    assert spec.report_name_exact == "반기보고서 (2026.06)"
    assert spec.discovery_begin_date == date(2026, 8, 10)
    assert spec.discovery_end_date == date(2026, 8, 14)
    assert spec.period_start == date(2026, 4, 1)
    assert spec.period_end == date(2026, 6, 30)


def test_discovery_requires_one_exact_non_correction_periodic_filing() -> None:
    frame = pd.DataFrame([_row(), _row(receipt="20260814009999", correction=True)])
    found = discover_periodic_product_revenue(_FakeDisclosureClient(frame), _spec())  # type: ignore[arg-type]
    assert found.rcept_no == RECEIPT

    duplicate = pd.DataFrame([_row(), _row(receipt="20260814001235")])
    with pytest.raises(ValueError, match="exact disclosure match must be unique"):
        discover_periodic_product_revenue(_FakeDisclosureClient(duplicate), _spec())  # type: ignore[arg-type]


def test_parser_uses_current_three_month_direct_rows_and_preserves_other() -> None:
    metrics = parse_periodic_product_revenue_text(_spec(), _text())
    assert metrics.unit == "KRW_million"
    assert metrics.dram_total == 28_900_000
    assert metrics.nand_and_solutions == 10_700_000
    assert metrics.other_products_services == 400_000
    assert metrics.reported_company_revenue == 40_000_000
    assert metrics.direct_sum == 40_000_000
    assert metrics.reconciliation_delta == 0


def test_parser_fails_closed_on_missing_other_or_nonreconciling_total() -> None:
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_periodic_product_revenue_text(_spec(), _text().replace("기타\n400,000", "서비스\n400,000"))
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_periodic_product_revenue_text(_spec(), _text().replace("40,000,000", "40,100,000", 1))


def test_direct_product_revenue_can_certify_revenue_baseline_but_not_profit_or_forecast() -> None:
    discovery = DiscoveredPeriodicProductRevenue(
        spec=_spec(),
        corp=_corp(),
        rcept_no=RECEIPT,
        report_name=_spec().report_name_exact,
        receipt_date=date(2026, 8, 14),
    )
    archive = _archive()
    certification = build_periodic_product_revenue_certification(
        discovery,
        archive,
        evaluation_date=EVALUATION,
    )
    assert certification.source_archive_bytes_archived is True
    assert certification.direct_product_revenue_semantics_certified is True
    assert certification.other_amount_certified is True
    assert certification.company_revenue_reconciliation_certified is True
    assert certification.product_revenue_baseline_eligible is True
    assert certification.allocation_resolver_registered is False
    assert certification.product_profitability_certified is False
    assert certification.numeric_forecast_enabled is False
    assert certification.decision_score_enabled is False
    assert hashlib.sha256(archive.archive_bytes).hexdigest() == certification.archive_sha256
