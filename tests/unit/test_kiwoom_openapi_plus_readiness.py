"""Tests for Kiwoom OpenAPI+ installation inspection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alpha_cycle import kiwoom_openapi_plus_readiness_cli as readiness


def _write_pe(path: Path, machine: int) -> None:
    payload = bytearray(512)
    payload[0:2] = b"MZ"
    payload[0x3C:0x40] = (0x80).to_bytes(4, byteorder="little")
    payload[0x80:0x84] = b"PE\x00\x00"
    payload[0x84:0x86] = machine.to_bytes(2, byteorder="little")
    path.write_bytes(payload)


def _registered(_arguments: object) -> readiness.CommandResult:
    return readiness.CommandResult(
        returncode=0,
        stdout=r"HKEY_CLASSES_ROOT\KHOPENAPI.KHOpenAPICtrl.1",
        stderr="",
    )


def test_detect_pe_architecture_without_loading_binary(tmp_path: Path) -> None:
    x86 = tmp_path / "x86.ocx"
    x64 = tmp_path / "x64.ocx"
    unknown = tmp_path / "unknown.ocx"
    _write_pe(x86, 0x014C)
    _write_pe(x64, 0x8664)
    unknown.write_bytes(b"not-a-pe")

    assert readiness.detect_pe_architecture(x86) == "x86"
    assert readiness.detect_pe_architecture(x64) == "x64"
    assert readiness.detect_pe_architecture(unknown) == "unknown"


def test_x86_ocx_with_64_bit_python_requires_bridge(tmp_path: Path) -> None:
    root = tmp_path / "OpenAPI"
    root.mkdir()
    _write_pe(root / "KHOpenAPI.ocx", 0x014C)

    report = readiness.inspect_openapi_plus(
        explicit_root=root,
        environ={},
        system_name="Windows",
        python_bitness=64,
        runner=_registered,
    )

    assert report.status == "passed_bridge_required"
    assert report.ocx_registered is True
    assert report.ocx_architecture == "x86"
    assert report.direct_python_compatible is False
    assert report.bridge_required is True
    assert report.login_verified is False
    assert report.account_api_enabled is False
    assert report.order_api_enabled is False


def test_matching_python_bitness_passes(tmp_path: Path) -> None:
    root = tmp_path / "OpenAPI"
    root.mkdir()
    _write_pe(root / "KHOpenAPI.ocx", 0x014C)
    (root / "KOAStudioSA.exe").write_bytes(b"optional")

    report = readiness.inspect_openapi_plus(
        explicit_root=root,
        environ={},
        system_name="Windows",
        python_bitness=32,
        runner=_registered,
    )

    assert report.status == "passed"
    assert report.koa_studio_present is True
    assert report.direct_python_compatible is True
    assert report.bridge_required is False


def test_missing_registration_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "OpenAPI"
    root.mkdir()
    _write_pe(root / "KHOpenAPI.ocx", 0x014C)

    report = readiness.inspect_openapi_plus(
        explicit_root=root,
        environ={},
        system_name="Windows",
        python_bitness=32,
        runner=lambda _arguments: readiness.CommandResult(1, "", "not found"),
    )

    assert report.status == "ocx_not_registered"
    assert report.ocx_registered is False
    assert report.market_data_enabled is False


def test_non_windows_is_explicitly_unsupported() -> None:
    report = readiness.inspect_openapi_plus(
        environ={},
        system_name="Linux",
        python_bitness=64,
    )

    assert report.status == "unsupported_platform"
    assert report.installation_root is None
    assert report.order_api_enabled is False


def test_cli_writes_installation_only_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = readiness.KiwoomOpenApiPlusReport(
        status="passed_bridge_required",
        system_name="Windows",
        installation_root="C:/OpenAPI",
        ocx_path="C:/OpenAPI/KHOpenAPI.ocx",
        ocx_registered=True,
        registry_evidence="progid",
        koa_studio_present=False,
        python_bitness=64,
        ocx_architecture="x86",
        direct_python_compatible=False,
        bridge_required=True,
        login_verified=False,
        service_registration_verified=False,
        market_data_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=("bridge required",),
    )
    monkeypatch.setattr(readiness, "inspect_openapi_plus", lambda **_kwargs: report)
    output = tmp_path / "readiness.json"

    result = readiness.main(["--output", str(output)])

    assert result == 0
    printed = capsys.readouterr().out
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "KIWOOM OPENAPI+ INSTALLATION: PASS" in printed
    assert "App Key" not in printed
    assert "App Secret" not in printed
    assert payload["login_verified"] is False
    assert payload["order_api_enabled"] is False


def test_windows_launcher_never_prompts_for_rest_credentials() -> None:
    powershell = Path("scripts/check_kiwoom_openapi_plus.ps1").read_text(
        encoding="utf-8"
    )
    command = Path("scripts/check_kiwoom_openapi_plus.cmd").read_text(
        encoding="utf-8"
    )

    combined = powershell + command
    assert "Read-Host" not in combined
    assert "APP_KEY" not in combined
    assert "APP_SECRET" not in combined
    assert "kiwoom_openapi_plus_readiness_cli" in combined
