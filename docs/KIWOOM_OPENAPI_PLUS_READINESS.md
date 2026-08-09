# Kiwoom OpenAPI+ readiness

Alpha Cycle Lab treats Kiwoom OpenAPI+ and Kiwoom REST API as separate products.

- **OpenAPI+**: installed Windows COM/OCX module. It uses the Kiwoom login window
  and TR/event calls through the installed control.
- **REST API**: separately applied-for web API. It uses an App Key, App Secret,
  registered IP address, and OAuth token.

Installing OpenAPI+ does not create REST credentials. The project therefore does
not ask an OpenAPI+ user for App Key or App Secret files.

## Installation check

Run from the repository root:

```powershell
.\scripts\check_kiwoom_openapi_plus.cmd
```

The command checks, without opening the login window:

- Windows platform
- `C:\OpenAPI` or `C:\OpenApi` installation directory
- `KHOpenAPI.ocx` presence
- `KHOPENAPI.KHOpenAPICtrl.1` COM registration
- OCX PE architecture
- current Python process bitness
- optional `KOAStudioSA.exe` presence

No account ID, password, certificate, REST key, or OpenAPI+ login information is
requested or stored.

If OpenAPI+ was installed elsewhere:

```powershell
.\scripts\check_kiwoom_openapi_plus.cmd -InstallRoot "D:\OpenAPI"
```

## Result meanings

### `passed`

The OCX is present, registered, and its architecture matches the current Python
process.

### `passed_bridge_required`

The OpenAPI+ installation is valid, but the OCX architecture and the repository's
current Python process have different bitness. The correct integration is a
separate compatible Windows bridge process. The main environment is not replaced
or downgraded merely to host the OCX.

## Isolated x86 bridge

When the installation check returns `passed_bridge_required`, configure the bridge:

```powershell
.\scripts\setup_kiwoom_openapi_plus_bridge.cmd -InstallPython
```

The command:

1. Locates an existing Python 3.10, 3.11, or 3.12 x86 interpreter.
2. With `-InstallPython`, may install official Python 3.12 x86 through `winget` when
   no compatible interpreter is present.
3. Creates `.venv-kiwoom-x86` without changing the main project environment.
4. Installs pinned Windows x86 PyQt5 ActiveX dependencies only.
5. Creates `KHOPENAPI.KHOpenAPICtrl.1` without opening the login window.
6. Leaves account, holdings, balance, and order functions disabled.

The isolated runtime intentionally does not install the main package, NumPy, or
pandas. It exists only to host the 32-bit ActiveX control.

Recheck the configured bridge without login:

```powershell
.\scripts\check_kiwoom_openapi_plus_bridge.cmd
```

Expected status:

```text
KIWOOM OPENAPI+ BRIDGE: PASS
status: passed_environment
ActiveX control created: True
connected: False
account API: disabled
order API: disabled
```

## Interactive login probe

After the environment check passes, verify OpenAPI+ service registration and the
login event:

```powershell
.\scripts\login_probe_kiwoom_openapi_plus.cmd -TimeoutSeconds 600
```

The official Kiwoom login window opens. The bridge calls only:

- `CommConnect()`
- `OnEventConnect`
- `GetConnectState()`

It does not call account-information or order functions. Login credentials are
handled by the official Kiwoom window and are not read or stored by the project.
A successful result is:

```text
KIWOOM OPENAPI+ BRIDGE: PASS
status: passed_login
connected: True
service registration verified: True
market data session ready: True
account API: disabled
order API: disabled
```

## Read-only adjusted market export

After the bridge can log in, collect an independent Kiwoom market snapshot:

```powershell
.\scripts\export_kiwoom_openapi_plus_market.cmd
```

The default universe matches the current live market pipeline:

- `005930`: Samsung Electronics common
- `005935`: Samsung Electronics preferred, retained as auxiliary valuation evidence
- `000660`: SK hynix

The exporter performs two sequential public-market TR requests per symbol:

- `opt10001`: current quote and basic price fields
- `opt10081`: daily chart, first response page only

The hardened daily-bar path requests **`수정주가구분=1`**. Each accepted daily bar
is marked as adjusted and is bound to separate adjustment-response evidence. The
export preserves the raw adjustment code, adjustment ratio, adjustment event, and
previous-close response fields instead of assuming that the requested basis alone
proves adjustment.

The downstream Kiwoom-primary adapter fails closed unless all of the following are
true:

- pointer and manifest both declare `adjusted_prices=true`;
- pointer and manifest both declare `price_basis=adjusted`;
- the manifest records `adjustment_request_value=1`;
- every accepted daily bar has matching adjustment evidence;
- the symbol set is exactly `000660`, `005930`, `005935`;
- account and order APIs remain disabled;
- the export is fresh enough for the primary-market adapter.

Prices are normalized to non-negative OHLC values while exact provider strings are
retained beside the normalized values. A negative signed current-price string is
therefore not discarded or hidden.

The exporter enforces conservative rolling request gates and serializes requests in
one ActiveX process.

A successful run writes:

```text
data/private/live-research/kiwoom-openapi-plus-market/
  latest_market_export.json
  <capture timestamp>/
    manifest.json
    quotes.csv
    daily_bars.csv
    <adjustment evidence file recorded by manifest>
```

The manifest records, among other fields:

- provider and snapshot ID
- UTC and Korea capture timestamps
- exact symbol set
- quote and bar counts
- TR codes and request count
- adjusted-price status and requested adjustment value
- adjustment-evidence file binding
- source messages and explicit limitations
- disabled account and order capabilities

Optional overrides:

```powershell
.\scripts\export_kiwoom_openapi_plus_market.cmd `
    -Symbols 005930,005935,000660 `
    -DailyCount 120 `
    -TimeoutSeconds 600
```

## Live-pipeline fallback behavior

For a normal Windows live run, use the repository launcher:

```powershell
.\scripts\run_live_pipeline.cmd
```

The direct Python module is the TossInvest market-source path. When the supported
Windows launcher observes a sanitized `tossinvest_ip_allowlist` blocker (or a
resume-unavailable state), the orchestrator can explicitly collect a **new**
Kiwoom read-only adjusted export and then run the pipeline in
`Kiwoom-primary-only` mode.

This is not silent source substitution. The orchestrator checks that the Kiwoom
bundle is newly captured, has the expected provider and symbols, stays inside the
configured output root, keeps account/order APIs disabled, and then sends it
through the Kiwoom primary provenance gate. If a new valid bundle cannot be
published, no single-provider decision is published.

The standalone exporter also remains usable independently; creating an export by
itself does not automatically replace another provider.

## Deliberate limits

The installation, login, market-export, and fallback tools do not enable:

- account-number lookup
- holdings or balance collection
- certificate or account-password collection
- order placement, cancellation, or modification
- automatic trading from the exported evidence
- unmarked or provenance-free source replacement

The bridge environment result is written locally to:

```text
data/private/live-research/kiwoom_openapi_plus_bridge_readiness.json
```

The earlier installation-only result remains at:

```text
data/private/live-research/kiwoom_openapi_plus_readiness.json
```

PyQt5 is installed only in the isolated x86 environment. Its upstream GPL or
commercial licensing terms apply independently of the Alpha Cycle Lab repository.
