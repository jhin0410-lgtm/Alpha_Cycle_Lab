"""Regression checks for late runtime-boundary Codex findings."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _load_kiwoom_bootstrap() -> ModuleType:
    path = Path("bridge/kiwoom_openapi_plus/market_export_bootstrap.py")
    spec = importlib.util.spec_from_file_location(
        "test_kiwoom_market_export_bootstrap",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kiwoom_bootstrap_exits_from_write_export_not_return_trace() -> None:
    bootstrap = Path(
        "bridge/kiwoom_openapi_plus/market_export_bootstrap.py"
    ).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in bootstrap
    assert "main(exit_before_teardown=True)" in bootstrap
    assert "_install_success_exit" in bootstrap
    assert "write_export_and_exit" in bootstrap
    assert "_run_entrypoint_with_success_exit" in bootstrap
    assert "exit_process(code)" in bootstrap
    assert "sys.settrace" not in bootstrap
    assert "raise SystemExit(main())" not in bootstrap


def test_kiwoom_bootstrap_exits_while_exporter_frame_locals_are_alive() -> None:
    bootstrap = _load_kiwoom_bootstrap()
    state: dict[str, object] = {
        "destroyed": False,
        "exit_code": None,
    }
    output = io.StringIO()

    class BridgeExit(BaseException):
        pass

    class Sentinel:
        def __del__(self) -> None:
            state["destroyed"] = True

    manifest = SimpleNamespace(
        snapshot_id="a" * 64,
        symbols=("005930", "000660"),
        quote_count=2,
        daily_bar_count=240,
        adjusted_prices=False,
        request_count=4,
    )

    def write_export() -> tuple[object, Path]:
        return manifest, Path("immutable-evidence")

    runtime_globals: dict[str, object] = {"write_export": write_export}

    def entrypoint() -> int:
        sentinel = Sentinel()
        assert sentinel is not None
        runtime_globals["write_export"]()
        raise AssertionError("hard exit must prevent normal return")

    def fake_exit(code: int) -> None:
        state["exit_code"] = code
        assert state["destroyed"] is False
        raise BridgeExit

    with pytest.raises(BridgeExit):
        bootstrap._run_entrypoint_with_success_exit(
            entrypoint,
            runtime_globals,
            exit_process=fake_exit,
            stdout=output,
            stderr=io.StringIO(),
        )

    assert state["exit_code"] == 0
    assert "KIWOOM OPENAPI+ MARKET EXPORT: PASS" in output.getvalue()
    assert f"snapshot: {'a' * 64}" in output.getvalue()


def test_kiwoom_bootstrap_does_not_mask_unexpected_entrypoint_exception() -> None:
    bootstrap = _load_kiwoom_bootstrap()
    exit_codes: list[int] = []

    def write_export() -> tuple[object, Path]:
        raise AssertionError("write_export should not be reached")

    runtime_globals: dict[str, object] = {"write_export": write_export}

    def broken_entrypoint() -> int:
        raise RuntimeError("unexpected bridge failure")

    def fake_exit(code: int) -> None:
        exit_codes.append(code)
        raise AssertionError("unexpected hard exit")

    with pytest.raises(RuntimeError, match="unexpected bridge failure"):
        bootstrap._run_entrypoint_with_success_exit(
            broken_entrypoint,
            runtime_globals,
            exit_process=fake_exit,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert exit_codes == []


def test_kiwoom_bootstrap_preserves_handled_failure_status() -> None:
    bootstrap = _load_kiwoom_bootstrap()
    exit_codes: list[int] = []

    def write_export() -> tuple[object, Path]:
        raise AssertionError("write_export should not be reached")

    runtime_globals: dict[str, object] = {"write_export": write_export}

    def failed_entrypoint() -> int:
        return 2

    class BridgeExit(BaseException):
        pass

    def fake_exit(code: int) -> None:
        exit_codes.append(code)
        raise BridgeExit

    with pytest.raises(BridgeExit):
        bootstrap._run_entrypoint_with_success_exit(
            failed_entrypoint,
            runtime_globals,
            exit_process=fake_exit,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert exit_codes == [2]


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
