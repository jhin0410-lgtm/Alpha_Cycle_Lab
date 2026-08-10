"""Bootstrap isolated unadjusted Kiwoom valuation-history export on Windows x86."""

from __future__ import annotations

import importlib.util
import json
import runpy
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, TextIO


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load Kiwoom bridge module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _print_success(
    manifest: Any,
    export_directory: Any,
    *,
    json_output: bool,
    stdout: TextIO,
) -> None:
    if json_output:
        print(
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
        return
    print("KIWOOM OPENAPI+ VALUATION HISTORY EXPORT: PASS", file=stdout)
    print(f"snapshot: {manifest.snapshot_id}", file=stdout)
    print(f"symbols: {', '.join(manifest.symbols)}", file=stdout)
    print(f"daily bars: {manifest.daily_bar_count}", file=stdout)
    print(f"price basis: {manifest.price_basis}", file=stdout)
    print(f"adjustment request: {manifest.adjustment_request_value}", file=stdout)
    print(f"requests: {manifest.request_count}", file=stdout)
    print("primary market evidence: disabled", file=stdout)
    print("technical indicator use: disabled", file=stdout)
    print("decision score: disabled", file=stdout)
    print("account API: disabled", file=stdout)
    print("order API: disabled", file=stdout)
    print(f"export directory: {export_directory}", file=stdout)


def main(
    *,
    exit_before_teardown: bool = True,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> Any:
    directory = Path(__file__).resolve().parent
    exporter_path = directory / "market_export.py"
    hardening_path = directory / "valuation_history_export_hardening.py"
    bootstrap_helper_path = directory / "market_export_bootstrap.py"
    for path in (exporter_path, hardening_path, bootstrap_helper_path):
        if not path.is_file():
            raise FileNotFoundError(f"Kiwoom bridge dependency is missing: {path.name}")

    helper = _load_module(
        "alpha_cycle_kiwoom_market_bootstrap_helper",
        bootstrap_helper_path,
    )
    helper.ensure_export_timezones()
    namespace = runpy.run_path(
        str(exporter_path),
        run_name="alpha_cycle_kiwoom_valuation_history_export",
    )
    entrypoint = namespace.get("main")
    if not callable(entrypoint):
        raise RuntimeError("Kiwoom market exporter has no callable main")
    runtime_globals = entrypoint.__globals__
    hardening = _load_module(
        "alpha_cycle_kiwoom_valuation_history_hardening",
        hardening_path,
    )
    hardening.apply_hardening(runtime_globals)
    sys.argv[0] = str(exporter_path)

    if not exit_before_teardown:
        return entrypoint()

    original_write = runtime_globals.get("write_export")
    if not callable(original_write):
        raise RuntimeError("Kiwoom valuation-history exporter has no writer")
    output = stdout if stdout is not None else sys.stdout
    error = stderr if stderr is not None else sys.stderr
    json_output = "--json" in sys.argv[1:]

    def write_export_and_exit(*args: Any, **kwargs: Any) -> NoReturn:
        manifest, export_directory = original_write(*args, **kwargs)
        _print_success(
            manifest,
            export_directory,
            json_output=json_output,
            stdout=output,
        )
        helper._flush_and_hard_exit(  # noqa: SLF001 - shared Windows bridge primitive
            0,
            stdout=output,
            stderr=error,
        )

    runtime_globals["write_export"] = write_export_and_exit
    result = entrypoint()
    helper._flush_and_hard_exit(  # noqa: SLF001 - shared Windows bridge primitive
        0 if result is None else int(result),
        stdout=output,
        stderr=error,
    )


if __name__ == "__main__":
    main()
