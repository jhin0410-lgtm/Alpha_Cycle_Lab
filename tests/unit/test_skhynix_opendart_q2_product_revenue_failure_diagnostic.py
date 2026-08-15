from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_failure_diagnostic import (
    diagnose_failure,
    latest_failure_diagnostic,
)


def _archive() -> bytes:
    markup = """
    <html><body>
      <h2>연결재무제표 주석</h2>
      <p>5. 매출액</p><p>당반기</p><p>(단위 : 백만원)</p>
      <table>
        <tr>
          <th></th>
          <th colspan="2">DRAM</th>
          <th colspan="2">NAND Flash</th>
          <th colspan="2">기타</th>
          <th colspan="2">부문 합계</th>
        </tr>
        <tr>
          <th>구분</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
        </tr>
        <tr>
          <td>수익(매출액)</td>
          <td>730</td><td>1400</td>
          <td>260</td><td>500</td>
          <td>10</td><td>20</td>
          <td>1000</td><td>1920</td>
        </tr>
      </table>
    </body></html>
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", markup)
    return buffer.getvalue()


def test_diagnostic_reports_relevant_text_and_table_shape(tmp_path: Path) -> None:
    failure = tmp_path / "failed" / "20260815__20260814003509"
    failure.mkdir(parents=True)
    raw = _archive()
    text = "\n".join(
        [
            "연결재무제표 주석",
            "5. 매출액",
            "당반기",
            "(단위 : 백만원)",
            "DRAM",
            "3개월",
            "누적",
            "NAND Flash",
            "3개월",
            "누적",
            "기타",
            "3개월",
            "누적",
            "부문 합계",
            "3개월",
            "누적",
            "수익(매출액)",
            "730",
            "1400",
            "260",
            "500",
            "10",
            "20",
            "1000",
            "1920",
        ]
    )
    archive_path = failure / "opendart_document.zip"
    text_path = failure / "normalized_document.txt"
    archive_path.write_bytes(raw)
    text_path.write_text(text, encoding="utf-8")
    payload = {
        "status": "skhynix_opendart_q2_product_revenue_parse_failed",
        "rcept_no": "20260814003509",
        "report_name": "반기보고서 (2026.06)",
        "archive_path": str(archive_path),
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_text_path": str(text_path),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "error": "candidates=0",
    }
    diagnostic = failure / "diagnostic.json"
    diagnostic.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    report = diagnose_failure(diagnostic)
    assert report.rcept_no == "20260814003509"
    assert report.normalized_text_contexts
    assert len(report.relevant_tables) == 1
    table = report.relevant_tables[0]
    assert table["rows"] == 3
    contains = table["contains"]
    assert isinstance(contains, dict)
    assert contains["dram"] is True
    assert contains["nand"] is True
    assert latest_failure_diagnostic(tmp_path) == diagnostic
