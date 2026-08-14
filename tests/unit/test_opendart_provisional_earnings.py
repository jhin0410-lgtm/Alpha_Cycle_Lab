from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from alpha_cycle.intelligence.opendart_provisional_earnings import (
    DiscoveredProvisionalDisclosure,
    build_provisional_earnings_evidence,
    discover_provisional_disclosure,
    load_provisional_earnings_registry,
    parse_provisional_earnings_text,
)
from alpha_cycle.providers.opendart import CorpCode, DisclosureBatch
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentEvidence,
    DisclosureDocumentMemberEvidence,
)

EVALUATION = date(2026, 8, 14)
DOCUMENT_ID = "skhynix_000660_2026q2_provisional"
RECEIPT = "20260729800013"


def _spec():
    return load_provisional_earnings_registry()[DOCUMENT_ID]


def _text() -> str:
    return "\n".join(
        [
            "연결재무제표기준영업(잠정)실적(공정공시)",
            "(단위 : 백만원, %)",
            "매출액",
            "당해실적",
            "79,318,746",
            "전기실적",
            "52,576,300",
            "전기대비증감율(%)",
            "50.9",
            "전년동기실적",
            "16,423,300",
            "누계실적",
            "131,895,046",
            "영업이익",
            "당해실적",
            "60,542,608",
            "전기실적",
            "37,610,300",
            "전기대비증감율(%)",
            "61.0",
            "전년동기실적",
            "5,468,500",
            "누계실적",
            "98,152,908",
            "법인세비용차감전계속사업이익",
            "당해실적",
            "100,000,000",
            "누계실적",
            "140,000,000",
            "당기순이익",
            "당해실적",
            "93,922,593",
            "전기실적",
            "40,345,900",
            "전년동기실적",
            "4,120,000",
            "누계실적",
            "134,268,493",
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
        assert begin_date == end_date == date(2026, 7, 29)
        return DisclosureBatch(self.frame, raw_payload={"pages": []})


def _row(*, receipt: str = RECEIPT, report_name: str | None = None, correction: bool = False):
    return {
        "ticker": "000660",
        "corp_code": "00164779",
        "corp_name": "SK하이닉스",
        "rcept_no": receipt,
        "report_name": report_name or _spec().report_name_exact,
        "receipt_date": date(2026, 7, 29),
        "corp_class": "Y",
        "is_correction": correction,
    }


def _document(text: str | None = None) -> DisclosureDocumentEvidence:
    body = text if text is not None else _text()
    text_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return DisclosureDocumentEvidence(
        rcept_no=RECEIPT,
        retrieved_at=datetime(2026, 8, 14, 6, 0, tzinfo=UTC),
        archive_sha256="a" * 64,
        archive_bytes=4096,
        member_count=1,
        text_member_count=1,
        uncompressed_bytes=8192,
        text_sha256=text_hash,
        text_chars=len(body),
        text_truncated=False,
        text=body,
        members=(
            DisclosureDocumentMemberEvidence(
                name="document.xml",
                sha256="b" * 64,
                compressed_bytes=4096,
                uncompressed_bytes=8192,
                encoding="utf-8",
                text_chars=len(body),
            ),
        ),
        warnings=(),
    )


def test_registry_keeps_sk_hynix_provisional_actual_company_level_only() -> None:
    spec = _spec()
    assert spec.ticker == "000660"
    assert spec.receipt_date == date(2026, 7, 29)
    assert spec.consolidated_only is True
    assert spec.audited is False
    assert spec.product_baseline_eligible is False


def test_discovery_requires_one_exact_non_correction_open_dart_disclosure() -> None:
    frame = pd.DataFrame([_row(), _row(receipt="20260729999999", correction=True)])
    found = discover_provisional_disclosure(_FakeDisclosureClient(frame), _spec())  # type: ignore[arg-type]
    assert found.rcept_no == RECEIPT
    assert found.report_name == _spec().report_name_exact

    duplicate = pd.DataFrame([_row(), _row(receipt="20260729800014")])
    with pytest.raises(ValueError, match="exact disclosure match must be unique"):
        discover_provisional_disclosure(_FakeDisclosureClient(duplicate), _spec())  # type: ignore[arg-type]


def test_parser_reads_current_quarter_company_actuals_not_prior_or_cumulative_values() -> None:
    metrics = parse_provisional_earnings_text(_spec(), _text())
    assert metrics.unit == "KRW_million"
    assert metrics.revenue == 79_318_746
    assert metrics.operating_income == 60_542_608
    assert metrics.net_income == 93_922_593


def test_parser_requires_registered_unit_and_current_period_markers() -> None:
    with pytest.raises(ValueError, match="allowed KRW unit"):
        parse_provisional_earnings_text(_spec(), _text().replace("백만원", "달러"))
    with pytest.raises(ValueError, match="current-period marker"):
        parse_provisional_earnings_text(
            _spec(),
            _text().replace("매출액\n당해실적", "매출액\n미정"),
        )


def test_evidence_is_provisional_company_actual_but_never_product_baseline() -> None:
    discovery = DiscoveredProvisionalDisclosure(
        spec=_spec(),
        corp=_corp(),
        rcept_no=RECEIPT,
        report_name=_spec().report_name_exact,
        receipt_date=date(2026, 7, 29),
    )
    evidence = build_provisional_earnings_evidence(
        discovery,
        _document(),
        evaluation_date=EVALUATION,
    )
    assert evidence.metrics.revenue == 79_318_746
    assert evidence.company_level_actual is True
    assert evidence.provisional is True
    assert evidence.audited is False
    assert evidence.product_baseline_eligible is False
    assert evidence.source_archive_bytes_archived is False
    assert evidence.normalized_document_text_archived is True
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_truncated_original_document_is_rejected() -> None:
    discovery = DiscoveredProvisionalDisclosure(
        spec=_spec(),
        corp=_corp(),
        rcept_no=RECEIPT,
        report_name=_spec().report_name_exact,
        receipt_date=date(2026, 7, 29),
    )
    document = _document()
    truncated = DisclosureDocumentEvidence(
        **{**document.__dict__, "text_truncated": True},
    )
    with pytest.raises(ValueError, match="refuses truncated"):
        build_provisional_earnings_evidence(
            discovery,
            truncated,
            evaluation_date=EVALUATION,
        )
