"""Regression checks for late runtime-boundary Codex findings."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType

import pytest


def _load_kiwoom_bootstrap() -> ModuleType:
    path = Path("bridge/kiwoom_openapi_plus/market_export_bootstrap.py")
    spec = importlib.util.spec_from_file_location("test_kiwoom_market_export_bootstrap", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kiwoom_bootstrap_propagates_exporter_exit_status_before_teardown() -> None:
    bootstrap = Path(
        "bridge/kiwoom_openapi_plus/market_export_bootstrap.py"
    ).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in bootstrap
    assert "main(exit_before_teardown=True)" in bootstrap
    assert "_run_entrypoint_before_teardown" in bootstrap
    assert "sys.settrace(trace)" in bootstrap
    assert "exit_process(code)" in bootstrap
    assert "result = main()" not in bootstrap
    assert "raise SystemExit(main())" not in bootstrap


def test_kiwoom_bootstrap_exits_while_exporter_frame_locals_are_alive() -> None:
    bootstrap = _load_kiwoom_bootstrap()
    state: dict[str, object] = {
        "destroyed": False,
        "exit_code": None,
    }

    class BridgeExit(BaseException):
        pass

    class Sentinel:
        def __del__(self) -> None:
            state["destroyed"] = True

    def entrypoint() -> int:
        sentinel = Sentinel()
        assert sentinel is not None
        return 7

    def fake_exit(code: int) -> None:
        state["exit_code"] = code
        assert state["destroyed"] is False
        raise BridgeExit

    with pytest.raises(BridgeExit):
        bootstrap._run_entrypoint_before_teardown(
            entrypoint,
            exit_process=fake_exit,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert state["exit_code"] == 7


def test_kiwoom_bootstrap_does_not_mask_unexpected_entrypoint_exception() -> None:
    bootstrap = _load_kiwoom_bootstrap()
    exit_codes: list[int] = []

    def broken_entrypoint() -> int:
        raise RuntimeError("unexpected bridge failure")

    def fake_exit(code: int) -> None:
        exit_codes.append(code)
        raise AssertionError("unexpected hard exit")

    with pytest.raises(RuntimeError, match="unexpected bridge failure"):
        bootstrap._run_entrypoint_before_teardown(
            broken_entrypoint,
            exit_process=fake_exit,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert exit_codes == []


def test_windows_pipeline_helpers_accept_default_empty_arguments() -> None:
    script = Path("scripts/run_live_pipeline.ps1").read_text(encoding="utf-8")

    assert script.count("[AllowEmptyCollection()]") >= 4
    assert "[string[]]$PipelineArguments = @()" in script
    for function_name in (
        "Get-PipelineOptionValue",
        "New-ResumeArguments",
        "Resolve-OutputRoot",
    ):
        section = script[script.index(f"function {function_name}") :]
        assert "[AllowEmptyCollection()]" in section.split("}", 1)[0]
