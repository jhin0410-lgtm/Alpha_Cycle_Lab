from __future__ import annotations

import io
import json
import zipfile
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
from alpha_cycle.providers.opendart import CorpCode, DisclosureBatch

EVALUATION = date(2026, 8, 14)
RECEIPT = "20260814001234"
DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


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


def _zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", f"<html><body>{_text().replace(chr(10), '<br>')}</body></html>")
    return buffer.getvalue()


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body


class _Client:
    def __init__(self) -> None:
        self.raw = _zip()

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


def _capture(tmp_path: Path) -> Path:
    spec = load_periodic_product_revenue_registry()[DOCUMENT_ID]
    capture_periodic_product_revenue_certification(
        _Client(),  # type: ignore[arg-type]
        spec,
        evaluation_date=EVALUATION,
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
    )
    return tmp_path / "latest_certification.json"


def test_verifier_replays_archived_zip_and_parser(tmp_path: Path) -> None:
    pointer = _capture(tmp_path)
    item = load_periodic_product_revenue_certification(
        pointer,
        evaluation_date=EVALUATION,
    )
    assert item.metrics.other_products_services == 400_000
    assert item.product_revenue_baseline_eligible is True
    assert item.numeric_forecast_enabled is False


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
