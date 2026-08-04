# Windows Python environments

Alpha Cycle Lab uses two deliberately separate Python environments on Windows.

## Main analysis environment

The main project requires Python 3.12 or newer, 64-bit. It runs:

- market consistency checks
- live research pipeline
- valuation and decision modules
- NumPy and pandas workloads
- local test and quality tooling

Configure it from the repository root:

```powershell
.\scripts\setup_project_python.cmd -InstallPython
```

The setup command:

1. Finds an existing compatible 64-bit Python.
2. When `-InstallPython` is supplied and none exists, installs official Python
   3.12 x64 through WinGet.
3. Creates `.venv` from the x64 interpreter.
4. Installs the project and development dependencies with editable packaging.
5. Verifies 64-bit pointer width, core imports, and `Asia/Seoul` timezone data.
6. sets `ALPHA_CYCLE_PYTHON` to `.venv\Scripts\python.exe` for the current user.

Rebuild the main virtual environment when it exists but is incompatible:

```powershell
.\scripts\setup_project_python.cmd -InstallPython -Force
```

After setup:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\scripts\resolve_project_python.ps1"

.\scripts\check_market_source_consistency.cmd
```

The resolver should return `.venv\Scripts\python.exe` or another verified x64
Python. It must not return a path containing `.venv-kiwoom-x86` or
`Python312-32`.

## Kiwoom OpenAPI+ bridge environment

Kiwoom OpenAPI+ uses a 32-bit OCX on this machine. Its isolated bridge remains:

```text
.venv-kiwoom-x86
```

Only the Kiwoom login and market-export commands use that environment. It does
not replace the main analysis environment.

## Why both environments are required

A 32-bit ActiveX host is required to load the installed Kiwoom OCX, while the
main project uses 64-bit scientific Python packages and Windows timezone data.
Mixing the two environments can cause missing dependency, architecture, and
`ZoneInfo` failures. The launchers therefore resolve the main x64 interpreter
explicitly and the Kiwoom scripts resolve the x86 bridge explicitly.

Account, holdings, balance, and order APIs remain disabled in the Kiwoom bridge.
