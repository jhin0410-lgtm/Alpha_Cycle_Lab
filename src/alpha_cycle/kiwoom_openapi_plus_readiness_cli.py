"""Inspect a local Kiwoom OpenAPI+ COM/OCX installation without credentials.

The command is intentionally installation-only. It does not open the Kiwoom login
window, query an account, request market data, or expose order methods.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import struct
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_OUTPUT_PATH = Path(
    "data/private/live-research/kiwoom_openapi_plus_readiness.json"
)
DEFAULT_INSTALL_ROOTS = (Path("C:/OpenAPI"), Path("C:/OpenApi"))
OPENAPI_PROGID = "KHOPENAPI.KHOpenAPICtrl.1"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[Sequence[str]], CommandResult]


@dataclass(frozen=True)
class KiwoomOpenApiPlusReport:
    status: str
    system_name: str
    installation_root: str | None
    ocx_path: str | None
    ocx_registered: bool
    registry_evidence: str | None
    koa_studio_present: bool
    python_bitness: int
    ocx_architecture: str
    direct_python_compatible: bool | None
    bridge_required: bool
    login_verified: bool
    service_registration_verified: bool
    market_data_enabled: bool
    account_api_enabled: bool
    order_api_enabled: bool
    warnings: tuple[str, ...]


def _default_runner(arguments: Sequence[str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandResult(
        returncode=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _candidate_roots(
    *,
    explicit_root: Path | None,
    environ: Mapping[str, str],
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(explicit_root.expanduser())
    configured = environ.get("KIWOOM_OPENAPI_HOME", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(DEFAULT_INSTALL_ROOTS)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).replace("\\", "/").casefold().rstrip("/")
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def _find_named_file(root: Path, filename: str) -> Path | None:
    if not root.is_dir():
        return None
    expected = filename.casefold()
    direct = root / filename
    if direct.is_file():
        return direct
    try:
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.name.casefold() == expected:
                return candidate
    except OSError:
        return None
    return None


def detect_pe_architecture(path: Path) -> str:
    """Read the PE machine field without loading or executing the OCX file."""
    try:
        raw = path.read_bytes()
    except OSError:
        return "unreadable"
    if len(raw) < 0x40 or raw[:2] != b"MZ":
        return "unknown"
    pe_offset = int.from_bytes(raw[0x3C:0x40], byteorder="little", signed=False)
    if pe_offset < 0 or pe_offset + 6 > len(raw):
        return "unknown"
    if raw[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return "unknown"
    machine = int.from_bytes(
        raw[pe_offset + 4 : pe_offset + 6], byteorder="little", signed=False
    )
    return {
        0x014C: "x86",
        0x8664: "x64",
        0xAA64: "arm64",
    }.get(machine, f"machine_0x{machine:04x}")


def _check_registration(runner: CommandRunner) -> tuple[bool, str | None]:
    commands = (
        ("reg.exe", "query", rf"HKCR\{OPENAPI_PROGID}"),
        (
            "reg.exe",
            "query",
            r"HKCR\WOW6432Node\CLSID",
            "/f",
            "KHOPENAPI",
            "/s",
        ),
    )
    for arguments in commands:
        try:
            result = runner(arguments)
        except (OSError, ValueError):
            continue
        combined = f"{result.stdout}\n{result.stderr}".casefold()
        if result.returncode == 0 and "khopenapi" in combined:
            evidence = "progid" if OPENAPI_PROGID.casefold() in combined else "wow6432_clsid"
            return True, evidence
    return False, None


def inspect_openapi_plus(
    *,
    explicit_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    system_name: str | None = None,
    python_bitness: int | None = None,
    runner: CommandRunner | None = None,
) -> KiwoomOpenApiPlusReport:
    values = os.environ if environ is None else environ
    resolved_system = platform.system() if system_name is None else system_name
    resolved_bitness = struct.calcsize("P") * 8 if python_bitness is None else python_bitness
    warnings: list[str] = []

    if resolved_system != "Windows":
        return KiwoomOpenApiPlusReport(
            status="unsupported_platform",
            system_name=resolved_system,
            installation_root=None,
            ocx_path=None,
            ocx_registered=False,
            registry_evidence=None,
            koa_studio_present=False,
            python_bitness=resolved_bitness,
            ocx_architecture="unknown",
            direct_python_compatible=None,
            bridge_required=False,
            login_verified=False,
            service_registration_verified=False,
            market_data_enabled=False,
            account_api_enabled=False,
            order_api_enabled=False,
            warnings=("Kiwoom OpenAPI+ is a Windows COM/OCX service.",),
        )

    root = next(
        (
            candidate
            for candidate in _candidate_roots(
                explicit_root=explicit_root,
                environ=values,
            )
            if candidate.is_dir()
        ),
        None,
    )
    if root is None:
        return KiwoomOpenApiPlusReport(
            status="installation_not_found",
            system_name=resolved_system,
            installation_root=None,
            ocx_path=None,
            ocx_registered=False,
            registry_evidence=None,
            koa_studio_present=False,
            python_bitness=resolved_bitness,
            ocx_architecture="unknown",
            direct_python_compatible=None,
            bridge_required=False,
            login_verified=False,
            service_registration_verified=False,
            market_data_enabled=False,
            account_api_enabled=False,
            order_api_enabled=False,
            warnings=(
                "No OpenAPI+ installation directory was found. Use --install-root when installed outside C:\\OpenAPI.",
            ),
        )

    ocx = _find_named_file(root, "KHOpenAPI.ocx")
    koa_studio = _find_named_file(root, "KOAStudioSA.exe") is not None
    if ocx is None:
        return KiwoomOpenApiPlusReport(
            status="ocx_not_found",
            system_name=resolved_system,
            installation_root=str(root),
            ocx_path=None,
            ocx_registered=False,
            registry_evidence=None,
            koa_studio_present=koa_studio,
            python_bitness=resolved_bitness,
            ocx_architecture="unknown",
            direct_python_compatible=None,
            bridge_required=False,
            login_verified=False,
            service_registration_verified=False,
            market_data_enabled=False,
            account_api_enabled=False,
            order_api_enabled=False,
            warnings=("KHOpenAPI.ocx was not found below the installation directory.",),
        )

    registered, registry_evidence = _check_registration(runner or _default_runner)
    architecture = detect_pe_architecture(ocx)
    direct_compatible: bool | None
    if architecture == "x86":
        direct_compatible = resolved_bitness == 32
    elif architecture == "x64":
        direct_compatible = resolved_bitness == 64
    else:
        direct_compatible = None
    bridge_required = direct_compatible is False

    if not registered:
        status = "ocx_not_registered"
        warnings.append("The OpenAPI+ COM registration was not found in the Windows registry.")
    elif bridge_required:
        status = "passed_bridge_required"
        warnings.append(
            "The installed OCX and current Python process have different bitness; use a separate compatible bridge process."
        )
    elif direct_compatible is None:
        status = "passed_unverified_bitness"
        warnings.append("The OCX PE architecture could not be identified safely.")
    else:
        status = "passed"

    if not koa_studio:
        warnings.append("KOA Studio was not found; it is optional and distributed separately.")
    warnings.append(
        "Installation inspection does not prove OpenAPI+ service registration or a successful Kiwoom login."
    )

    return KiwoomOpenApiPlusReport(
        status=status,
        system_name=resolved_system,
        installation_root=str(root),
        ocx_path=str(ocx),
        ocx_registered=registered,
        registry_evidence=registry_evidence,
        koa_studio_present=koa_studio,
        python_bitness=resolved_bitness,
        ocx_architecture=architecture,
        direct_python_compatible=direct_compatible,
        bridge_required=bridge_required,
        login_verified=False,
        service_registration_verified=False,
        market_data_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=tuple(warnings),
    )


def _write_report(report: KiwoomOpenApiPlusReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kiwoom-openapi-plus-ready",
        description="Inspect the installed Kiwoom OpenAPI+ COM/OCX module without login or credentials",
    )
    parser.add_argument("--install-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_openapi_plus(explicit_root=args.install_root)
    _write_report(report, args.output)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        success = report.status.startswith("passed")
        stream = sys.stdout if success else sys.stderr
        label = "PASS" if success else "FAIL"
        print(f"KIWOOM OPENAPI+ INSTALLATION: {label}", file=stream)
        print(f"status: {report.status}", file=stream)
        print(f"installation root: {report.installation_root}", file=stream)
        print(f"OCX registered: {report.ocx_registered}", file=stream)
        print(f"OCX architecture: {report.ocx_architecture}", file=stream)
        print(f"Python bitness: {report.python_bitness}", file=stream)
        print(f"bridge required: {report.bridge_required}", file=stream)
        print("login verified: false", file=stream)
        print("account API: disabled", file=stream)
        print("order API: disabled", file=stream)
        for warning in report.warnings:
            print(f"warning: {warning}", file=stream)
        print(f"readiness artifact: {args.output}", file=stream)
    return 0 if report.status.startswith("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
