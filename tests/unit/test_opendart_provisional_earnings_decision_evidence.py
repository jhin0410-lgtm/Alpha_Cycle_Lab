from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    load_opendart_provisional_earnings_decision_evidence,
)

EVALUATION = date(2026, 8, 14)
DOCUMENT_ID = "skhynix_000660_2026q2_provisional"
RECEIPT = "20260729800013"
TEXT = "\n".join(
    [
        "연결재무제표기준영업(잠정)실적(공정공시)",
        "(단위 : 백만원, %)",
        "매출액",
        "당해실적",
        "79,318,746",
        "누계실적",
        "131,895,046",
        "영업이익",
        "당해실적",
        "60,542,608",
        "누계실적",
        "98,152,908",
        "당기순이익",
        "당해실적",
        "93,922,593",
        "누계실적",
        "134,268,493",
    ]
)


def _false_flags() -> dict[str, object]:
    return {
        "product_baseline_eligible": False,
        "source_archive_bytes_archived": False,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }


def _pointer(tmp_path: Path) -> Path:
    root = tmp_path / "provisional"
    root.mkdir()
    evidence_id = "a" * 64
    text_hash = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
    archive_hash = "b" * 64
    payload = {
        **_false_flags(),
        "evidence_id": evidence_id,
        "evaluation_date": EVALUATION.isoformat(),
        "document_id": DOCUMENT_ID,
        "ticker": "000660",
        "issuer_name": "SK hynix",
        "rcept_no": RECEIPT,
        "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
        "receipt_date": "2026-07-29",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "unit": "KRW_million",
        "revenue": 79_318_746,
        "operating_income": 60_542_608,
        "net_income": 93_922_593,
        "archive_sha256": archive_hash,
        "archive_bytes": 4096,
        "text_sha256": text_hash,
        "text_chars": len(TEXT),
        "member_count": 1,
        "text_member_count": 1,
        "source_receipt_certified": True,
        "parser_semantics_certified": True,
        "provisional": True,
        "audited": False,
        "company_level_actual": True,
        "normalized_document_text_archived": True,
    }
    earnings_path = root / "provisional_earnings.json"
    earnings_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    text_path = root / "normalized_document.txt"
    text_path.write_text(TEXT, encoding="utf-8")
    metadata_path = root / "document_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "text_sha256": text_hash,
                "text_truncated": False,
                "source_archive_bytes_archived": False,
                "normalized_document_text_archived": True,
            }
        ),
        encoding="utf-8",
    )
    pointer = {
        **_false_flags(),
        "status": "opendart_provisional_earnings_captured",
        "evidence_id": evidence_id,
        "evaluation_date": EVALUATION.isoformat(),
        "document_id": DOCUMENT_ID,
        "ticker": "000660",
        "rcept_no": RECEIPT,
        "manifest_path": str(manifest_path),
        "provisional_earnings_path": str(earnings_path),
        "normalized_document_path": str(text_path),
        "document_metadata_path": str(metadata_path),
        "company_level_actual": True,
        "normalized_document_text_archived": True,
    }
    pointer_path = root / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_loader_reparses_normalized_original_text_before_accepting_actuals(tmp_path: Path) -> None:
    evidence = load_opendart_provisional_earnings_decision_evidence(
        _pointer(tmp_path),
        evaluation_date=EVALUATION,
    )
    assert evidence.ticker == "000660"
    assert evidence.metrics.revenue == 79_318_746
    assert evidence.metrics.operating_income == 60_542_608
    assert evidence.metrics.net_income == 93_922_593
    assert evidence.company_level_actual is True
    assert evidence.product_baseline_eligible is False
    assert evidence.decision_score_enabled is False
    assert evidence.numeric_forecast_enabled is False


def test_loader_rejects_normalized_text_tampering(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    text_path = Path(raw["normalized_document_path"])
    text_path.write_text(TEXT.replace("79,318,746", "1"), encoding="utf-8")
    with pytest.raises(ValueError, match="normalized document hash mismatch"):
        load_opendart_provisional_earnings_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_loader_rejects_any_product_baseline_promotion(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    raw["product_baseline_eligible"] = True
    pointer.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="product_baseline_eligible=false"):
        load_opendart_provisional_earnings_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_loader_requires_exact_live_evaluation_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        load_opendart_provisional_earnings_decision_evidence(
            _pointer(tmp_path),
            evaluation_date=date(2026, 8, 15),
        )
