from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_cycle import official_semiconductor_ir_refresh_cli as refresh_cli
from alpha_cycle.intelligence.official_semiconductor_ir_refresh import (
    build_official_ir_refresh_plan,
)


def test_refresh_plan_selects_samsung_and_preserves_sk_hynix_gap() -> None:
    plan = build_official_ir_refresh_plan(evaluation_date=date(2026, 8, 14))
    by_ticker = {item.ticker: item for item in plan.issuers}
    assert by_ticker["005930"].selected_document_id == "samsung_005930_2026q2_earnings"
    assert by_ticker["005930"].selected_period_end == date(2026, 6, 30)
    assert by_ticker["000660"].selected_document_id is None
    assert by_ticker["000660"].status == "unresolved_no_registered_document"
    assert "2Q26" in str(by_ticker["000660"].reason)


def test_refresh_plan_does_not_use_document_before_publication() -> None:
    plan = build_official_ir_refresh_plan(evaluation_date=date(2026, 7, 29))
    by_ticker = {item.ticker: item for item in plan.issuers}
    assert by_ticker["005930"].selected_document_id is None
    assert by_ticker["005930"].status == "unresolved_no_registered_document"


def _fake_collector_result(tmp_path: Path) -> dict[str, object]:
    artifact = tmp_path / "document-artifact"
    artifact.mkdir(parents=True)
    source = artifact / "source_document.pdf"
    source.write_bytes(b"%PDF-fake")
    baseline = artifact / "baseline_fact_pack.json"
    baseline.write_text(
        json.dumps(
            {
                "facts": [
                    {
                        "ticker": "005930",
                        "scope_id": "sdc",
                        "metric_id": "revenue",
                        "value": 7.5,
                        "unit": "KRW_trillion",
                        "period_start": "2026-04-01",
                        "period_end": "2026-06-30",
                        "source_id": "samsung_ir",
                        "source_url": "https://www.samsung.com/example",
                        "source_published_date": "2026-07-30",
                        "source_document_path": str(source),
                        "semantics_certified": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    forward = artifact / "forward_input_claim_pack.json"
    forward.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "ticker": "005930",
                        "block_id": "ds_memory",
                        "claim_type": "forward_driver",
                        "metric_id": "hbm_volume_and_mix",
                        "evidence_kind": "qualitative",
                        "statement": "bounded source claim",
                        "period_start": "2026-07-01",
                        "period_end": "2026-12-31",
                        "source_id": "samsung_ir",
                        "source_url": "https://www.samsung.com/example",
                        "source_published_date": "2026-07-30",
                        "source_document_path": str(source),
                        "parser_id": "samsung_earnings_presentation_2026q2_v2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "source_document_sha256": "a" * 64,
        "artifact_directory": str(artifact),
        "baseline_fact_pack_path": str(baseline),
        "forward_input_claim_pack_path": str(forward),
    }


def _fake_downstream_result(root: Path, name: str) -> dict[str, object]:
    artifact = root / name
    artifact.mkdir(parents=True)
    return {"artifact_directory": str(artifact)}


def test_refresh_builds_downstream_evidence_from_collected_document_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    collected = _fake_collector_result(tmp_path)
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        refresh_cli,
        "capture_official_ir_document",
        lambda *_args, **_kwargs: collected,
    )

    def fake_baseline(rows, **kwargs):
        seen["baseline"] = rows
        return _fake_downstream_result(Path(kwargs["output"]), "baseline-artifact")

    def fake_forward(rows, **kwargs):
        seen["forward"] = rows
        return _fake_downstream_result(Path(kwargs["output"]), "forward-artifact")

    def fake_accounting(pointer, **kwargs):
        seen["accounting_pointer"] = Path(pointer)
        return _fake_downstream_result(Path(kwargs["output"]), "accounting-artifact")

    monkeypatch.setattr(refresh_cli, "capture_semiconductor_baseline_reconciliation", fake_baseline)
    monkeypatch.setattr(refresh_cli, "capture_forward_input_evidence", fake_forward)
    monkeypatch.setattr(refresh_cli, "capture_semiconductor_accounting_identity", fake_accounting)
    result = refresh_cli.refresh_official_semiconductor_ir(
        evaluation_date=date(2026, 8, 14),
        output=tmp_path / "refresh",
        document_output=tmp_path / "documents",
        baseline_output=tmp_path / "baseline",
        forward_output=tmp_path / "forward",
        accounting_output=tmp_path / "accounting",
    )
    assert result["status"] == "partial"
    assert result["selected_document_ids"] == ["samsung_005930_2026q2_earnings"]
    assert len(result["collected"]) == 1
    assert result["failed"] == []
    assert result["downstream_failures"] == []
    assert result["unresolved"][0]["ticker"] == "000660"
    assert len(seen["baseline"]) == 1
    assert len(seen["forward"]) == 1
    assert str(seen["accounting_pointer"]).endswith(
        "latest_samsung_005930_2026q2_earnings.json"
    )
    assert result["accounting_identity_pointer"] is not None
    assert result["operating_assumptions_generated"] is False
    assert result["scenario_probabilities_enabled"] is False
    assert result["numeric_forecast_enabled"] is False
    assert result["decision_score_enabled"] is False


def test_accounting_identity_failure_is_downstream_gap_not_source_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    collected = _fake_collector_result(tmp_path)
    monkeypatch.setattr(
        refresh_cli,
        "capture_official_ir_document",
        lambda *_args, **_kwargs: collected,
    )
    monkeypatch.setattr(
        refresh_cli,
        "capture_semiconductor_baseline_reconciliation",
        lambda _rows, **kwargs: _fake_downstream_result(
            Path(kwargs["output"]), "baseline-artifact"
        ),
    )
    monkeypatch.setattr(
        refresh_cli,
        "capture_forward_input_evidence",
        lambda _rows, **kwargs: _fake_downstream_result(
            Path(kwargs["output"]), "forward-artifact"
        ),
    )
    monkeypatch.setattr(
        refresh_cli,
        "capture_semiconductor_accounting_identity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("identity drift")),
    )
    result = refresh_cli.refresh_official_semiconductor_ir(
        evaluation_date=date(2026, 8, 14),
        output=tmp_path / "refresh",
        document_output=tmp_path / "documents",
        baseline_output=tmp_path / "baseline",
        forward_output=tmp_path / "forward",
        accounting_output=tmp_path / "accounting",
    )
    assert result["status"] == "partial"
    assert result["failed"] == []
    assert result["downstream_failures"][0]["layer"] == "accounting_identity"
    assert result["baseline_reconciliation_pointer"] is not None
    assert result["forward_input_pointer"] is not None
    assert result["accounting_identity_pointer"] is None


def test_latest_document_collection_failure_does_not_fallback_or_publish_downstream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        refresh_cli,
        "capture_official_ir_document",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("parser drift")),
    )
    result = refresh_cli.refresh_official_semiconductor_ir(
        evaluation_date=date(2026, 8, 14),
        output=tmp_path / "refresh",
        document_output=tmp_path / "documents",
        baseline_output=tmp_path / "baseline",
        forward_output=tmp_path / "forward",
        accounting_output=tmp_path / "accounting",
    )
    assert result["status"] == "unavailable"
    assert result["collected"] == []
    assert result["failed"][0]["document_id"] == "samsung_005930_2026q2_earnings"
    assert result["baseline_reconciliation_pointer"] is None
    assert result["forward_input_pointer"] is None
    assert result["accounting_identity_pointer"] is None
