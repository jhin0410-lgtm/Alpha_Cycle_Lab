"""Tests for immutable Kiwoom export artifact allocation."""

from __future__ import annotations

import importlib.util
import json
import runpy
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

HARDENING_PATH = Path(
    "bridge/kiwoom_openapi_plus/market_export_hardening.py"
)
EXPORTER_PATH = Path("bridge/kiwoom_openapi_plus/market_export.py")
BOOTSTRAP_PATH = Path(
    "bridge/kiwoom_openapi_plus/market_export_bootstrap.py"
)


def _load_hardening() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_market_export_hardening_artifact_test",
        HARDENING_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class StubRecord:
    ticker: str
    value: int


def test_hardening_replaces_only_gate_and_writer() -> None:
    hardening = _load_hardening()
    namespace = runpy.run_path(
        str(EXPORTER_PATH),
        run_name="kiwoom_export_hardening_namespace",
    )
    original_collector = namespace["collect_market_data"]

    hardening.apply_hardening(namespace)

    assert namespace["RequestGate"] is hardening.RollingRequestGate
    assert callable(namespace["write_export"])
    assert namespace["collect_market_data"] is original_collector


def test_writer_rejects_reuse_of_existing_snapshot_directory(tmp_path: Path) -> None:
    hardening = _load_hardening()
    namespace = runpy.run_path(
        str(EXPORTER_PATH),
        run_name="kiwoom_export_writer_namespace",
    )
    fixed = datetime(2026, 8, 4, 8, 0, 0, 123456, tzinfo=UTC)
    namespace["_capture_now"] = lambda zone: fixed.astimezone(zone)
    writer = hardening.build_immutable_writer(namespace)
    exporter = SimpleNamespace(
        login_event_code=0,
        connected=True,
        request_count=2,
        request_gate=SimpleNamespace(interval_seconds=0.25),
        provider_messages=(),
    )

    manifest, directory = writer(
        output_root=tmp_path,
        symbols=("005930",),
        daily_count=1,
        quotes=[StubRecord("005930", 1)],
        bars=[StubRecord("005930", 2)],
        exporter=exporter,
    )
    latest_before = (tmp_path / "latest_market_export.json").read_text(
        encoding="utf-8"
    )

    with pytest.raises(FileExistsError):
        writer(
            output_root=tmp_path,
            symbols=("005930",),
            daily_count=1,
            quotes=[StubRecord("005930", 1)],
            bars=[StubRecord("005930", 2)],
            exporter=exporter,
        )

    assert directory.name.startswith("20260804T170000123456+0900__")
    assert directory.name.endswith(manifest.snapshot_id[:12])
    assert (directory / "manifest.json").is_file()
    assert (directory / "quotes.csv").is_file()
    assert (directory / "daily_bars.csv").is_file()
    assert (
        tmp_path / "latest_market_export.json"
    ).read_text(encoding="utf-8") == latest_before
    latest = json.loads(latest_before)
    assert latest["snapshot_id"] == manifest.snapshot_id


def test_bootstrap_is_python_310_compatible_and_applies_hardening() -> None:
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert "from datetime import UTC" not in bootstrap
    assert "timezone.utc" in bootstrap
    assert 'run_name="alpha_cycle_kiwoom_market_export"' in bootstrap
    assert "hardening.apply_hardening(runtime_globals)" in bootstrap
    assert "market_export_hardening.py" in bootstrap
