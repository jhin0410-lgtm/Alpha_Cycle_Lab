from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_replay import (
    replay_historical_product_revenue_failure,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _spec() -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id="historical-failure-replay-test",
        ticker="000660",
        issuer_name="SK하이닉스",
        source_id="opendart",
        report_name_exact="분기보고서 (2025.03)",
        discovery_begin_date=date(2025, 5, 1),
        discovery_end_date=date(2025, 5, 31),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("DRAM", "NAND", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타", "기타 제품 및 서비스"),
            "reported_company_revenue": ("합계", "매출액 합계", "부문 합계"),
        },
    )


def _text() -> str:
    return "\n".join(
        [
            "21. 매출액 (연결)",
            "(단위: 백만원)",
            "당분기",
            "3개월",
            "DRAM",
            "100",
            "NAND Flash",
            "40",
            "기타",
            "10",
            "합계",
            "150",
        ]
    )


def _archive(*, valid_table: bool) -> bytes:
    if valid_table:
        html = """<html><body>
<p>21. 매출액 (연결)</p><p>(단위: 백만원)</p>
<table>
<tr><th>구분</th><th>당분기</th><th>전분기</th></tr>
<tr><th>구분</th><th>3개월</th><th>3개월</th></tr>
<tr><td>DRAM</td><td>100</td><td>80</td></tr>
<tr><td>NAND Flash</td><td>40</td><td>35</td></tr>
<tr><td>기타</td><td>10</td><td>8</td></tr>
<tr><td>합계</td><td>150</td><td>123</td></tr>
</table>
</body></html>"""
    else:
        html = "<html><body><p>no product revenue table</p></body></html>"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", html.encode("utf-8"))
    return stream.getvalue()


def _diagnostic(
    tmp_path: Path,
    *,
    archive_bytes: bytes,
) -> HistoricalProductRevenueFailureDiagnostic:
    text = _text()
    text_path = tmp_path / "normalized_document.txt"
    text_path.write_bytes(text.encode("utf-8"))
    archive_path = tmp_path / "opendart_document.zip"
    archive_path.write_bytes(archive_bytes)
    return HistoricalProductRevenueFailureDiagnostic(
        period_id="2025Q1",
        diagnostic_path=str(tmp_path / "diagnostic.json"),
        rcept_no="20250515002103",
        report_name="분기보고서 (2025.03)",
        archive_path=str(archive_path),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        normalized_text_path=str(text_path),
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        error_type="ValueError",
        error="historical parser candidates=2",
    )


def test_failure_replay_marks_period_recoverable_only_when_text_and_raw_agree(
    tmp_path: Path,
) -> None:
    replay = replay_historical_product_revenue_failure(
        _diagnostic(tmp_path, archive_bytes=_archive(valid_table=True)),
        _spec(),
    )

    assert replay.text_parse_succeeded is True
    assert replay.archive_parse_succeeded is True
    assert replay.parser_agreement is True
    assert replay.replay_recoverable is True
    assert replay.text_metrics == replay.archive_metrics
    assert replay.network_requested is False
    assert replay.source_fact_promoted is False
    assert replay.certification_created is False
    assert replay.numeric_forecast_enabled is False
    assert replay.decision_score_enabled is False


def test_failure_replay_stays_unresolved_when_only_text_parser_succeeds(
    tmp_path: Path,
) -> None:
    replay = replay_historical_product_revenue_failure(
        _diagnostic(tmp_path, archive_bytes=_archive(valid_table=False)),
        _spec(),
    )

    assert replay.text_parse_succeeded is True
    assert replay.archive_parse_succeeded is False
    assert replay.parser_agreement is False
    assert replay.replay_recoverable is False
    assert replay.archive_error is not None
    assert replay.source_fact_promoted is False
