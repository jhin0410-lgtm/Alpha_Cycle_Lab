# Kiwoom REST readiness

Alpha Cycle Lab supports a local-only Kiwoom REST authentication readiness check.
This is deliberately separate from the installed Open API+ module.

## Supported local files

The readiness adapter expects the two Kiwoom REST text files downloaded when the
REST API application is completed:

- App Key text file
- App Secret text file

Do not copy these files into the repository. The Windows setup stores only their
absolute paths in the current user's environment:

- `KIWOOM_REST_APP_KEY_FILE`
- `KIWOOM_REST_APP_SECRET_FILE`

The file contents, file names, account identifiers, and OAuth token are not written
to repository or readiness artifacts.

## One-time setup and authentication check

```powershell
.\scripts\check_kiwoom_rest.cmd
```

On the first run, enter the full path to each Kiwoom REST text file. A successful
live-host authentication prints:

```text
KIWOOM REST READINESS: PASS
account API: disabled
order API: disabled
```

The secret-free result is written locally to:

```text
data/private/live-research/kiwoom_rest_readiness.json
```

## Offline file validation

```powershell
.\scripts\check_kiwoom_rest.cmd -Offline
```

This verifies that the credential text files are readable and structurally valid
without requesting an OAuth token.

## Mock host

```powershell
.\scripts\check_kiwoom_rest.cmd -Mock
```

Live and mock App Keys are separate. Configure paths for the key pair that matches
the selected host before running the check.

## Safety boundary

Implemented:

- official Kiwoom live and mock REST hosts only
- OAuth client-credentials request only
- local text-file or direct environment credential loading
- secret-free readiness artifact

Not implemented:

- account-number lookup
- holdings or balance collection
- order placement, cancellation, or modification
- automatic substitution for TossInvest market evidence
- installed Open API+ COM/OCX control

A later integration may use separately verified read-only Kiwoom quote and
investor-flow endpoints as cross-provider evidence. It must preserve provider
provenance and fail closed on conflicting values.
