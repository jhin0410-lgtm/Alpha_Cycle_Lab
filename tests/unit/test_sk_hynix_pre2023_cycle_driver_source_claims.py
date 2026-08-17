from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_cycle_driver_source_claims import (
    build_pre2023_cycle_driver_profile,
)


def _diagnostic(tmp_path: Path, text: str) -> HistoricalProductRevenueFailureDiagnostic:
    text_path = tmp_path / "normalized.txt"
    archive_path = tmp_path / "source.zip"
    text_path.write_text(text, encoding="utf-8")
    archive_path.write_bytes(b"fixture archive")
    return HistoricalProductRevenueFailureDiagnostic(
        period_id="2022Q2",
        diagnostic_path=str(tmp_path / "diagnostic.json"),
        rcept_no="20220816001536",
        report_name="반기보고서 (2022.06)",
        archive_path=str(archive_path),
        archive_sha256=hashlib.sha256(b"fixture archive").hexdigest(),
        normalized_text_path=str(text_path),
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        error_type="ValueError",
        error="fixture parse failure",
        receipt_date=date(2022, 8, 16),
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220816001536",
        retrieved_at=datetime(2026, 8, 17, tzinfo=UTC),
        text_truncated=False,
        archive_bytes=len(b"fixture archive"),
        text_chars=len(text),
    )


def test_cycle_driver_claims_preserve_2022q2_issuer_language(tmp_path: Path) -> None:
    text = (
        "DRAM은 약 10%의 출하량 증가를 달성하였고, ASP는 전 분기 대비 "
        "한 자릿수 초반 하락하였습니다. NAND는 Solidigm 통합 기준, 전 분기 대비 "
        "한 자릿수 후반의 출하량 증가를 기록하였습니다. 본사 기준 출하량은 "
        "10% 초반 증가하였고, ASP는 Solidigm 통합 및 본사 기준 모두 전 분기 대비 "
        "한 자릿수 초반으로 상승하였습니다."
    )
    profile = build_pre2023_cycle_driver_profile(_diagnostic(tmp_path, text))

    normalized = {claim.normalized_interval_text for claim in profile.claims}
    assert "Around 10% Increase" in normalized
    assert "Low-single% Decrease" in normalized
    assert "High-single% Increase" in normalized
    assert "Low-teen% Increase" in normalized
    assert "Low-single% Increase" in normalized
    assert profile.dram_asp_claim_count >= 1
    assert profile.dram_bit_volume_claim_count >= 1
    assert profile.nand_asp_claim_count >= 1
    assert profile.nand_bit_volume_claim_count >= 1
    assert profile.source_language_four_field_coverage is True
    assert all(claim.issuer_driver_language_source_fact for claim in profile.claims)
    assert all(not claim.numeric_point_source_fact for claim in profile.claims)
    assert all(not claim.estimation_input_ready for claim in profile.claims)
    assert profile.four_field_driver_certified is False
    assert profile.fit_enabled is False
