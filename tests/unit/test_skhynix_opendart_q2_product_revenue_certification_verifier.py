from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    capture_periodic_product_revenue_certification,
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_contract import (
    bind_periodic_product_revenue_parser_contract,
)
from alpha_cycle.providers.opendart import CorpCode, DisclosureBatch

EVALUATION = date(2026, 8, 14)
RECEIPT = "20260814001234"
DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _markup(*, other_label: str = "기타") -> str:
    return f"""
    <html><body>
      <h1>반기보고서 (2026.06)</h1>
      <p>제품별 매출액</p>
      <p>(단위 : 백만원)</p>
      <table>
        <tr>
          <th rowspan="2">구분</th>
          <th colspan="2">당반기</th>
          <th colspan="2">전반기</th>
        </tr>
        <tr>
          <th>3개월</th><th>누적</th><th>3개월</th><th>누적</th>
        </tr>
        <tr>
          <td>DRAM</td><td>28,900,000</td><td>51,000,000</td>
          <td>16,000,000</td><td>30,000,000</td>
        </tr>
        <tr>
          <td>NAND</td><td>10,700,000</td><td>19,000,000</td>
          <td>7,000,000</td><td>13,000,000</td>
        </tr>
        <tr>
          <td>{other_label}</td><td>400,000</td><td>700,000</td>
          <td>300,000</td><td>500,000</td>
        </tr>
        <tr>
          <td>합계</td><td>40,000,000</td><td>70,700,000</td>
          <td>23,300,000</td><td>43,500,000</td>
        </tr>
      </table>
    </body></html>
    """


def _zip(*, other_label: str = "기타") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", _markup(other_label=other_label))
    return buffer.getvalue()


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body


class _Client:
    def __init__(self, *, other_label: str = "기타") -> None:
        self.raw = _zip(other_label=other_label)

    def resolve_stock_codes(self, symbols):
        assert list(symbols) == ["000660"]
        return {
            "000660": CorpCode(
                corp_code="00164779",
                corp_name="SK하이닉스",
                stock_code="000660",
                modify_date=date(2026, 1, 1),
            )
        }

    def disclosures(self, corp, *, begin_date, end_date):
        del corp, begin_date, end_date
        frame = pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "corp_code": "00164779",
                    "corp_name": "SK하이닉스",
                    "rcept_no": RECEIPT,
                    "report_name": "반기보고서 (2026.06)",
                    "receipt_date": EVALUATION,
                    "corp_class": "Y",
                    "is_correction": False,
                }
            ]
        )
        return DisclosureBatch(frame, raw_payload={"pages": []})

    def _url(self, path, params):
        assert path == "/api/document.xml"
        assert params == {"rcept_no": RECEIPT}
        return "https://opendart.fss.or.kr/api/document.xml"

    def _get(self, url):
        assert url == "https://opendart.fss.or.kr/api/document.xml"
        return _Response(self.raw)

    def now(self):
        return datetime(2026, 8, 14, 9, 0, tzinfo=UTC)


def _capture(
    tmp_path: Path,
    *,
    other_label: str = "기타",
    custom_contract: bool = False,
) -> Path:
    spec = load_periodic_product_revenue_registry()[DOCUMENT_ID]
    if custom_contract:
        labels = dict(spec.product_labels)
        labels["other_products_services"] = (other_label,)
        spec = replace(spec, product_labels=labels)
    capture_periodic_product_revenue_certification(
        _Client(other_label=other_label),  # type: ignore[arg-type]
        spec,
        evaluation_date=EVALUATION,
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
    )
    pointer = tmp_path / "latest_certification.json"
    bind_periodic_product_revenue_parser_contract(pointer, spec)
    return pointer


def test_verifier_replays_archived_zip_table_and_bound_parser_contract(tmp_path: Path) -> None:
    pointer = _capture(tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_payload["parser_contract_bound"] is True
    assert len(pointer_payload["parser_contract_sha256"]) == 64
    assert len(pointer_payload["chain_evidence_id"]) == 64

    item = load_periodic_product_revenue_certification(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert item.metrics.dram_total == 28_900_000
    assert item.metrics.nand_and_solutions == 10_700_000
    assert item.metrics.other_products_services == 400_000
    assert item.metrics.reported_company_revenue == 40_000_000
    assert item.product_revenue_baseline_eligible is True
    assert item.numeric_forecast_enabled is False


def test_verifier_uses_capture_contract_instead_of_current_registry(tmp_path: Path) -> None:
    pointer = _capture(
        tmp_path,
        other_label="기타수익",
        custom_contract=True,
    )
    item = load_periodic_product_revenue_certification(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert item.metrics.other_products_services == 400_000


def test_verifier_rejects_parser_contract_tamper(tmp_path: Path) -> None:
    pointer = _capture(tmp_path)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    contract_path = Path(payload["parser_contract_path"])
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["product_labels"]["other_products_services"] = ["변조"]
    contract_path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="parser contract hash mismatch"):
        load_periodic_product_revenue_certification(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_verifier_rejects_archived_zip_tamper(tmp_path: Path) -> None:
    pointer = _capture(tmp_path)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    archive_path = Path(payload["archive_path"])
    archive_path.write_bytes(archive_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="archived ZIP hash mismatch"):
        load_periodic_product_revenue_certification(
            pointer,
            evaluation_date=EVALUATION,
        )
