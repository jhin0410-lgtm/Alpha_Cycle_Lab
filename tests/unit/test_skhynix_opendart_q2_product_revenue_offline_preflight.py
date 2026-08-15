from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

from alpha_cycle.sk_hynix_opendart_q2_product_revenue_offline_preflight_cli import main


def _archive_bytes() -> bytes:
    html = """
    <html><body>
      <h1>반기보고서 (2026.06)</h1>
      <h3>21. 매출액 (연결)</h3>
      <p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>
      <p>당반기</p><p>(단위 : 백만원)</p>
      <table>
        <tr>
          <th rowspan="2">부문</th>
          <th colspan="2">DRAM</th>
          <th colspan="2">NAND Flash</th>
          <th colspan="2">기타</th>
          <th colspan="2">부문 합계</th>
        </tr>
        <tr>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
        </tr>
      </table>
      <table><tr><td>helper-layout</td></tr></table>
      <p>수익</p>
      <table><tr><td>56,982,743</td><td>97,641,379</td></tr></table>
      <table><tr><td>21,959,898</td><td>33,534,133</td></tr></table>
      <table><tr><td>376,105</td><td>719,521</td></tr></table>
      <table><tr><td>79,318,746</td><td>131,895,033</td></tr></table>
      <p>전반기</p>
    </body></html>
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", html)
    return buffer.getvalue()


def _normalized_text() -> str:
    return "\n".join(
        [
            "반기보고서 (2026.06)",
            "21. 매출액 (연결)",
            "고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익",
            "56,982,743",
            "97,641,379",
            "21,959,898",
            "33,534,133",
            "376,105",
            "719,521",
            "79,318,746",
            "131,895,033",
            "전반기",
        ]
    )


def test_offline_preflight_replays_preserved_raw_and_text_without_network(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    archive_path = tmp_path / "opendart_document.zip"
    text_path = tmp_path / "normalized_document.txt"
    archive_path.write_bytes(_archive_bytes())
    text_path.write_text(_normalized_text(), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "offline-preflight",
            "--archive",
            str(archive_path),
            "--normalized-text",
            str(text_path),
            "--registry",
            "config/semiconductor_periodic_product_revenue.yaml",
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "skhynix_opendart_q2_product_revenue_offline_preflight_passed"
    assert payload["network_requested"] is False
    assert payload["metrics"]["dram_total"] == 56_982_743
    assert payload["metrics"]["nand_and_solutions"] == 21_959_898
    assert payload["metrics"]["other_products_services"] == 376_105
    assert payload["metrics"]["reported_company_revenue"] == 79_318_746
