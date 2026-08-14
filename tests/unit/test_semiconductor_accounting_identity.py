from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence import semiconductor_accounting_identity as identity_module
from alpha_cycle.intelligence.semiconductor_accounting_identity import (
    build_samsung_accounting_identity_from_official_ir,
)
from alpha_cycle.semiconductor_accounting_identity_cli import (
    capture_semiconductor_accounting_identity,
)

EVALUATION = date(2026, 8, 14)
SOURCE = b"%PDF-synthetic-samsung-2q26-accounting-identity"


def _pages(*, include_intersegment: bool = True) -> tuple[str, ...]:
    pages = [""] * 16
    pages[4] = "2Q 2026 Results Based on consolidated financial statements Revenue 171.5"
    pages[5] = (
        "Results by Business Segment Total 171.5 DS 127.5 DX 48.0 SDC 7.5 Harman 4.6 "
        + (
            "sales of business units include intersegment sales"
            if include_intersegment
            else "segment sales footnote removed"
        )
    )
    pages[11] = """
    Appendix 1: 2Q 2026 Results & Financial Data
    KRW trillion 2Q 25 % of sales 1Q 26 % of sales 2Q 26 % of sales
    Sales 74.6 100.0% 133.9 100.0% 171.5 100.0%
    Operating profit 4.7 6.3% 57.2 42.8% 89.5 52.2%
    Profit before income tax 5.8 7.7% 58.8 43.9% 94.4 55.1%
    Income tax 0.6 - 11.6 - 22.8 -
    Net profit 5.1 6.9% 47.2 35.3% 71.6 41.8%
    """
    pages[12] = """
    Appendix 2: Results by Business Segment
    Sales Operating Profit
    Total 74.6 133.9 171.5 28% 130%
    DX 43.6 52.7 48.0 9% 10%
    DS 27.9 81.7 127.5 56% 357%
    SDC 6.4 6.7 7.5 12% 17%
    Harman 3.8 3.8 4.6 19% 19%
    Total 4.7 57.2 89.5 32.3 84.8
    DX 3.3 3.0 (0.8) 3.8 4.1
    DS 0.4 53.7 89.2 35.5 88.8
    SDC 0.5 0.4 0.7 0.3 0.2
    Harman 0.5 0.2 0.4 0.2 0.1
    """
    return tuple(pages)


def _pointer(tmp_path: Path) -> Path:
    root = tmp_path / "official-ir"
    root.mkdir()
    source_path = root / "source_document.pdf"
    source_path.write_bytes(SOURCE)
    source_hash = hashlib.sha256(SOURCE).hexdigest()
    false_flags = {
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    manifest = {
        **false_flags,
        "status": "official_semiconductor_ir_document_captured",
        "evaluation_date": EVALUATION.isoformat(),
        "document_id": "samsung_005930_2026q2_earnings",
        "ticker": "005930",
        "period_start": "2026-04-01",
        "period_end": "2026-06-30",
        "parser_semantics_certified": True,
        "source_document_sha256": source_hash,
        "source_bytes_archived": True,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pointer = {
        **false_flags,
        "status": "official_semiconductor_ir_document_captured",
        "evaluation_date": EVALUATION.isoformat(),
        "document_id": "samsung_005930_2026q2_earnings",
        "ticker": "005930",
        "source_document_sha256": source_hash,
        "source_document_path": str(source_path),
        "manifest_path": str(manifest_path),
        "source_bytes_archived": True,
    }
    pointer_path = root / "pointer.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_samsung_accounting_identity_uses_complete_same_document_company_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_module, "extract_pdf_pages", lambda _data: _pages())
    evidence = build_samsung_accounting_identity_from_official_ir(
        _pointer(tmp_path),
        evaluation_date=EVALUATION,
    )
    assert evidence.consolidated_revenue == 171.5
    assert evidence.segment_revenue_sum == pytest.approx(187.6)
    assert evidence.consolidation_revenue_adjustment == pytest.approx(-16.1)
    assert evidence.consolidated_operating_income == 89.5
    assert evidence.segment_operating_income_sum == pytest.approx(89.5)
    assert evidence.consolidation_operating_income_adjustment == pytest.approx(0.0)
    assert evidence.profit_before_tax == 94.4
    assert evidence.income_tax == 22.8
    assert evidence.net_income == 71.6
    assert evidence.non_operating_to_pbt_bridge == pytest.approx(4.9)
    assert evidence.corporate_consolidation_bridge_certified is True
    assert evidence.net_income_bridge_certified is True
    assert evidence.corporate_baseline_bridge_certified is True
    assert evidence.accounting_identity_derivation_enabled is True
    assert evidence.residual_estimate_enabled is False
    assert evidence.segment_profit_inference_enabled is False
    assert evidence.memory_operating_income_derived is False
    assert evidence.foundry_operating_income_derived is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_accounting_identity_requires_intersegment_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity_module,
        "extract_pdf_pages",
        lambda _data: _pages(include_intersegment=False),
    )
    with pytest.raises(ValueError, match="intersegment footnote"):
        build_samsung_accounting_identity_from_official_ir(
            _pointer(tmp_path),
            evaluation_date=EVALUATION,
        )


def test_accounting_identity_rejects_source_byte_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_module, "extract_pdf_pages", lambda _data: _pages())
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    Path(raw["source_document_path"]).write_bytes(SOURCE + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_samsung_accounting_identity_from_official_ir(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_accounting_identity_artifact_keeps_estimation_and_scoring_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity_module, "extract_pdf_pages", lambda _data: _pages())
    result = capture_semiconductor_accounting_identity(
        _pointer(tmp_path),
        evaluation_date=EVALUATION,
        output=tmp_path / "identity",
        captured_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )
    payload = json.loads(Path(str(result["accounting_identity_path"])).read_text(encoding="utf-8"))
    assert payload["corporate_baseline_bridge_certified"] is True
    assert payload["accounting_identity_derivation_enabled"] is True
    assert payload["residual_estimate_enabled"] is False
    assert payload["segment_profit_inference_enabled"] is False
    assert payload["memory_operating_income_derived"] is False
    assert payload["foundry_operating_income_derived"] is False
    assert payload["numeric_forecast_enabled"] is False
    assert payload["decision_score_enabled"] is False
