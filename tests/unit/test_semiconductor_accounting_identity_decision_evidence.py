from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence import semiconductor_accounting_identity_decision_evidence as decision_module
from alpha_cycle.intelligence.semiconductor_accounting_identity import (
    SamsungAccountingIdentityEvidence,
)
from alpha_cycle.intelligence.semiconductor_accounting_identity_decision_evidence import (
    load_semiconductor_accounting_identity_decision_evidence,
)

EVALUATION = date(2026, 8, 14)
EVIDENCE_ID = "a" * 64
SOURCE_ID = "b" * 64


def _evidence() -> SamsungAccountingIdentityEvidence:
    return SamsungAccountingIdentityEvidence(
        evidence_id=EVIDENCE_ID,
        evaluation_date=EVALUATION,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        source_document_sha256=SOURCE_ID,
        consolidated_revenue=171.5,
        segment_revenue_sum=187.6,
        consolidation_revenue_adjustment=-16.1,
        consolidated_operating_income=89.5,
        segment_operating_income_sum=89.5,
        consolidation_operating_income_adjustment=0.0,
        profit_before_tax=94.4,
        income_tax=22.8,
        net_income=71.6,
        non_operating_to_pbt_bridge=4.9,
        corporate_consolidation_bridge_certified=True,
        net_income_bridge_certified=True,
        corporate_baseline_bridge_certified=True,
    )


def _false_flags() -> dict[str, object]:
    return {
        "residual_estimate_enabled": False,
        "segment_profit_inference_enabled": False,
        "memory_operating_income_derived": False,
        "foundry_operating_income_derived": False,
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
    root = tmp_path / "identity"
    root.mkdir()
    payload_path = root / "accounting_identity.json"
    manifest_path = root / "manifest.json"
    official_pointer = root / "official.json"
    official_pointer.write_text("{}", encoding="utf-8")
    payload = {
        **_false_flags(),
        "evidence_id": EVIDENCE_ID,
        "corporate_baseline_bridge_certified": True,
    }
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = {
        **_false_flags(),
        "evidence_id": EVIDENCE_ID,
        "accounting_identity_derivation_enabled": True,
        "official_ir_pointer_path": str(official_pointer),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pointer = {
        **_false_flags(),
        "status": "semiconductor_accounting_identity_captured",
        "evidence_id": EVIDENCE_ID,
        "evaluation_date": EVALUATION.isoformat(),
        "ticker": "005930",
        "manifest_path": str(manifest_path),
        "accounting_identity_path": str(payload_path),
        "corporate_baseline_bridge_certified": True,
        "accounting_identity_derivation_enabled": True,
    }
    pointer_path = root / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_accounting_identity_loader_reconstructs_before_accepting_persisted_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Path] = []

    def fake_rebuild(path, *, evaluation_date):
        seen.append(Path(path))
        assert evaluation_date == EVALUATION
        return _evidence()

    monkeypatch.setattr(
        decision_module,
        "build_samsung_accounting_identity_from_official_ir",
        fake_rebuild,
    )
    evidence = load_semiconductor_accounting_identity_decision_evidence(
        _pointer(tmp_path),
        evaluation_date=EVALUATION,
    )
    assert evidence.evidence.evidence_id == EVIDENCE_ID
    assert len(seen) == 1
    assert evidence.evidence.corporate_baseline_bridge_certified is True
    assert evidence.decision_score_enabled is False
    assert evidence.numeric_forecast_enabled is False


def test_accounting_identity_loader_rejects_tampered_persisted_evidence_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        decision_module,
        "build_samsung_accounting_identity_from_official_ir",
        lambda *_args, **_kwargs: _evidence(),
    )
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    payload_path = Path(raw["accounting_identity_path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["evidence_id"] = "c" * 64
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="payload evidence mismatch"):
        load_semiconductor_accounting_identity_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_accounting_identity_loader_rejects_any_residual_estimate_flag(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    raw["residual_estimate_enabled"] = True
    pointer.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="residual_estimate_enabled=false"):
        load_semiconductor_accounting_identity_decision_evidence(
            pointer,
            evaluation_date=EVALUATION,
        )


def test_accounting_identity_loader_requires_exact_evaluation_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="evaluation date mismatch"):
        load_semiconductor_accounting_identity_decision_evidence(
            _pointer(tmp_path),
            evaluation_date=date(2026, 8, 15),
        )
