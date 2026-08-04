"""Tests for production Kiwoom rolling request limits."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

HARDENING_PATH = Path(
    "bridge/kiwoom_openapi_plus/market_export_hardening.py"
)


def _load_hardening() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_market_export_hardening_gate_test",
        HARDENING_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rolling_gate_enforces_minute_limit() -> None:
    hardening = _load_hardening()
    state = {"now": 0.0}
    sleeps: list[float] = []

    def clock() -> float:
        return state["now"]

    def sleeper(delay: float) -> None:
        sleeps.append(delay)
        state["now"] += delay

    gate = hardening.RollingRequestGate(clock=clock, sleeper=sleeper)
    for _ in range(101):
        gate.wait()

    assert any(delay >= 35.0 for delay in sleeps)
    assert state["now"] >= 60.0


def test_rolling_gate_enforces_hour_limit() -> None:
    hardening = _load_hardening()
    state = {"now": 0.0}
    sleeps: list[float] = []

    def clock() -> float:
        return state["now"]

    def sleeper(delay: float) -> None:
        sleeps.append(delay)
        state["now"] += delay

    gate = hardening.RollingRequestGate(
        per_minute=100,
        per_hour=3,
        clock=clock,
        sleeper=sleeper,
    )
    for _ in range(4):
        gate.wait()

    assert any(delay >= 3599.0 for delay in sleeps)
    assert state["now"] >= 3600.0
