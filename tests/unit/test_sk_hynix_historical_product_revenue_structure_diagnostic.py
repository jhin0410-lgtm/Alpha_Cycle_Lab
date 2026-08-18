from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_revenue_structure_diagnostic import (
    diagnose_failed_historical_product_revenue_structure,
)


def _write_failure_bundle(tmp_path: Path, period_id: str, html: str) -> Path:
    period_root = tmp_path / period_id
    bundle = period_root / "failed" / "20260818T000000000000Z__20180515000001"
    bundle.mkdir(parents=True)
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("document.html", html)
    archive_bytes = archive_buffer.getvalue()
    archive_path = bundle / "opendart_document.zip"
    archive_path.write_bytes(archive_bytes)
    normalized_text = html
    text_path = bundle / "normalized_document.txt"
    text_path.write_text(normalized_text, encoding="utf-8")
    payload = {
        "status": "skhynix_opendart_q2_product_revenue_parse_failed",
        "rcept_no": "20180515000001",
        "report_name": "분기보고서 (2018.03)",
        "archive_path": str(archive_path),
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "normalized_text_path": str(text_path),
        "text_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "error_type": "ValueError",
        "error": "synthetic parser failure for structure diagnostic test",
    }
    (bundle / "diagnostic.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return period_root


def test_structure_diagnostic_finds_shared_nonzero_label_column_without_certifying(
    tmp_path: Path,
) -> None:
    html = """
    <p>(단위: 백만원) 매출</p>
    <table>
      <tr><th></th><th>구분</th><th>당분기</th></tr>
      <tr><th></th><th>구분</th><th>3개월</th></tr>
      <tr><td></td><td>DRAM</td><td>60</td></tr>
      <tr><td></td><td>NAND Flash</td><td>30</td></tr>
      <tr><td></td><td>기타</td><td>10</td></tr>
      <tr><td></td><td>합계</td><td>100</td></tr>
    </table>
    """
    period_root = _write_failure_bundle(tmp_path, "2018Q1", html)
    result = diagnose_failed_historical_product_revenue_structure(
        "2018Q1",
        period_root,
    )

    assert result.product_token_table_count == 1
    assert result.current_recovery_shape_match_count == 0
    review = result.reviews[0]
    assert review.shared_four_label_columns == (1,)
    assert review.three_month_header_columns == (2,)
    assert review.current_period_header_columns == (2,)
    assert "dram_not_in_first_column" in review.structural_rejection_reasons
    assert "nand_not_in_first_column" in review.structural_rejection_reasons
    assert result.source_certification_promoted is False
    assert result.residual_other_derivation_allowed is False
    assert result.fit_enabled is False
    assert result.future_holdout_loaded is False
    assert result.future_holdout_evaluated is False


def test_structure_diagnostic_recognizes_source_backed_spaced_korean_other_label(
    tmp_path: Path,
) -> None:
    html = """
    <p>(단위: 백만원) 매출</p>
    <table>
      <tr><th>구분</th><th>당분기</th></tr>
      <tr><td>DRAM</td><td>60</td></tr>
      <tr><td>NAND Flash</td><td>30</td></tr>
      <tr><td>기 타</td><td>10</td></tr>
      <tr><td>합 계</td><td>100</td></tr>
    </table>
    """
    period_root = _write_failure_bundle(tmp_path, "2018Q1", html)
    result = diagnose_failed_historical_product_revenue_structure(
        "2018Q1",
        period_root,
    )

    review = result.reviews[0]
    assert review.other_label_columns == (0,)
    assert review.shared_four_label_columns == (0,)
    assert "other_not_in_first_column" not in review.structural_rejection_reasons
    assert review.current_recovery_shape_matches is True
    assert result.source_certification_promoted is False
    assert result.residual_other_derivation_allowed is False


def test_structure_diagnostic_never_derives_missing_other_as_residual(tmp_path: Path) -> None:
    html = """
    <p>(단위: 백만원) 매출</p>
    <table>
      <tr><th>구분</th><th>당분기</th></tr>
      <tr><th>구분</th><th>3개월</th></tr>
      <tr><td>DRAM</td><td>60</td></tr>
      <tr><td>NAND Flash</td><td>30</td></tr>
      <tr><td>합계</td><td>100</td></tr>
    </table>
    """
    period_root = _write_failure_bundle(tmp_path, "2017Q1", html)
    result = diagnose_failed_historical_product_revenue_structure(
        "2017Q1",
        period_root,
    )

    review = result.reviews[0]
    assert review.dram_label_columns == (0,)
    assert review.nand_label_columns == (0,)
    assert review.other_label_columns == ()
    assert review.total_label_columns == (0,)
    assert "other_not_in_first_column" in review.structural_rejection_reasons
    assert review.current_recovery_shape_matches is False
    assert result.source_certification_promoted is False
    assert result.residual_other_derivation_allowed is False
