"""Tests for the one-command live research pipeline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle import live_pipeline_cli as pipeline


def test_default_security_mapping_uses_classes_not_exact_console_text() -> None:
    mappings = pipeline._default_security_mappings()
    samsung = mappings["005930"].securities
    hynix = mappings["000660"].securities

    assert samsung["보통주"] == "005930"
    assert samsung["우선주"] == "005935"
    assert samsung["1우선주"] == "005935"
    assert samsung["Preferred Stock"] == "005935"
    assert hynix["Common Stock"] == "000660"
    assert "기타주식" not in samsung


def test_default_ecos_specs_follow_evaluation_date() -> None:
    specs = pipeline._default_ecos_specs(
        date(2026, 8, 1),
        lookback_days=31,
    )
    assert [spec.series_id for spec in specs] == ["kr_base_rate", "usd_krw"]
    assert all(spec.start == "20260701" for spec in specs)
    assert all(spec.end == "20260801" for spec in specs)


@pytest.mark.parametrize(
    "message",
    [
        "TossInvest HTTP 403: IP address not allowed",
        "auth request rejected: ip not allowed",
        "client IP is absent from the allowlist",
    ],
)
def test_ip_allowlist_error_classification(message: str) -> None:
    assert pipeline._is_ip_allowlist_error(message)


def test_unrelated_http_error_is_not_allowlist_error() -> None:
    assert not pipeline._is_ip_allowlist_error("TossInvest HTTP 401 invalid client")


def test_write_status_replaces_latest_run_atomically(tmp_path: Path) -> None:
    first = pipeline._write_status(tmp_path, {"status": "blocked"})
    second = pipeline._write_status(tmp_path, {"status": "completed"})
    assert first == second == tmp_path / "latest_run.json"
    assert json.loads(second.read_text(encoding="utf-8")) == {"status": "completed"}
    assert not (tmp_path / ".latest_run.json.tmp").exists()


def test_main_reports_public_ip_for_toss_allowlist_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def blocked(_: object) -> dict[str, object]:
        raise pipeline.PipelineStageError(
            "market",
            ValueError("TossInvest HTTP 403: IP address not allowed"),
        )

    monkeypatch.setattr(pipeline, "_execute", blocked)
    monkeypatch.setattr(pipeline, "_public_ip", lambda _: "203.0.113.10")

    result = pipeline.main(["--output", str(tmp_path)])

    assert result == 3
    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "blocked"
    assert payload["reason"] == "tossinvest_ip_allowlist"
    assert payload["public_ip"] == "203.0.113.10"
    assert payload["rerun_command"] == "python -m alpha_cycle.live_pipeline_cli"
    persisted = json.loads((tmp_path / "latest_run.json").read_text(encoding="utf-8"))
    assert persisted["public_ip"] == "203.0.113.10"
    assert "CLIENT" not in json.dumps(persisted)


def test_main_success_writes_latest_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        pipeline,
        "_execute",
        lambda _: {"status": "completed", "decision_snapshot_id": "a" * 64},
    )

    result = pipeline.main(["--output", str(tmp_path)])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert Path(payload["status_path"]).name == "latest_run.json"
    persisted = json.loads((tmp_path / "latest_run.json").read_text(encoding="utf-8"))
    assert persisted["decision_snapshot_id"] == "a" * 64
