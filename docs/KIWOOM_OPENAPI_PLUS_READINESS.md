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
separate compatible Windows bridge process that communicates with the main
pipeline through a narrow local protocol. The main environment should not be
replaced or downgraded merely to host the OCX.

### `ocx_not_registered`

The file exists but Windows COM registration could not be found. Reinstalling or
repairing the official OpenAPI+ module may be required.

### `installation_not_found` / `ocx_not_found`

The default directory was not found or does not contain `KHOpenAPI.ocx`. Supply
`-InstallRoot` when the official module was installed in another directory.

## Deliberate limits

This check does not prove:

- OpenAPI+ service-use registration on the Kiwoom account
- successful real or mock login
- certificate or account-password availability
- market-data permission
- account or order permission

Those require an interactive OpenAPI+ bridge and explicit user login. The first
bridge milestone will remain read-only and collect only source-provenanced market
and investor-flow evidence. Account queries and order submission stay disabled.

The local inspection result is written to:

```text
data/private/live-research/kiwoom_openapi_plus_readiness.json
```
