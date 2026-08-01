# One-command live research pipeline

`alpha-cycle-live` runs the current Samsung Electronics / Samsung Electronics preferred / SK hynix workflow without manual snapshot-path wiring.

## What it automates

One invocation performs these stages in order:

1. TossInvest read-only market prices and 100 daily candles for `005930`, `005935`, and `000660`;
2. OpenDART financial statements and disclosures for `005930` and `000660`;
3. Bank of Korea ECOS base-rate and USD/KRW series through the current Korea date;
4. OpenDART share counts and multi-period financial history;
5. complete market-capitalization checks across Samsung common and preferred shares;
6. valuation metrics and the integrated decision report;
7. `latest_run.json` with the status and every output directory.

The default evaluation date is the current date in `Asia/Seoul`. The annual financial reference defaults to the previous business year. ECOS and disclosure date ranges are calculated in memory, so `config/ecos_series.local.yaml` is not edited.

## Recommended Windows command

Use the repository launcher instead of calling the Python module directly:

```powershell
.\scripts\run_live_pipeline.cmd
```

The launcher:

- restores previously saved user-level credentials into the current process;
- starts secure one-time setup when any required credential is missing;
- runs the live pipeline from the repository root;
- reads `latest_run.json` safely;
- prints the report only when the pipeline completed and `report_path` exists.

The first run asks only for values that are not already configured:

```text
TOSSINVEST_CLIENT_ID
TOSSINVEST_CLIENT_SECRET
OPENDART_API_KEY
BOK_ECOS_API_KEY
```

`BOK_ECOS_API_KEY` is the canonical Bank of Korea key name for this repository. The older internal alias `ECOS_API_KEY` is still accepted and migrated automatically, but users do not need to rename an existing `BOK_ECOS_API_KEY` variable.

The values are stored in the current Windows user's environment and copied into the current PowerShell process. They are not written to repository files, printed, or committed. As with all user-level environment variables, other processes running as the same Windows user may be able to read them.

Credential status can be checked without displaying values:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\setup_local_credentials.ps1 `
  -StatusOnly
```

Replace existing saved values intentionally:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\setup_local_credentials.ps1 `
  -Force
```

Suppress automatic report output while still running the pipeline:

```powershell
.\scripts\run_live_pipeline.cmd -NoReport
```

Additional arguments are forwarded to the Python pipeline:

```powershell
.\scripts\run_live_pipeline.cmd `
  --evaluation-date 2026-08-01 `
  --history-years 3
```

## Direct Python command

The direct command remains available when the required environment variables already exist. Package startup maps `BOK_ECOS_API_KEY` to the process-local compatibility alias expected by the ECOS provider.

```powershell
python -m alpha_cycle.live_pipeline_cli
```

Equivalent installed entry point:

```powershell
alpha-cycle-live
```

Default output root:

```text
data/private/live-research
```

Successful runs print a JSON object containing:

- market, research, valuation, and decision snapshot IDs;
- each immutable snapshot directory;
- the final `report.md` path;
- complete-market-cap and valuation-score counts;
- decision-state counts and warnings.

The same object is saved to:

```text
data/private/live-research/latest_run.json
```

## TossInvest IP allowlist blocker

A TossInvest response containing `IP address not allowed` is not treated as a credential typo. The command:

1. stops before creating linked downstream snapshots;
2. performs a best-effort public IPv4 lookup through `https://api.ipify.org`;
3. writes a sanitized blocker record to `latest_run.json`;
4. tells the operator to register that public IP in the TossInvest Open API client allowlist;
5. provides the exact rerun command.

No client ID, secret, OpenDART key, or ECOS key is written to disk or printed.

Disable the public-IP lookup when required:

```powershell
python -m alpha_cycle.live_pipeline_cli --no-public-ip-lookup
```

The TossInvest account allowlist remains an external account setting and cannot be changed by this repository.

## Security-class mapping

The pipeline uses an in-memory class mapping:

```text
005930 common    -> 005930
005930 preferred -> 005935
000660 common    -> 000660
```

It classifies OpenDART security labels by common/preferred meaning, so the workflow does not depend on a Korean-text YAML file being rendered correctly by Windows PowerShell 5.1.

`config/security_mappings.example.yaml` remains available for standalone valuation runs. Its Korean keys are represented with YAML Unicode escapes so the file itself is ASCII-safe while PyYAML still resolves the exact Korean labels.

## Optional arguments

```powershell
python -m alpha_cycle.live_pipeline_cli `
  --evaluation-date 2026-08-01 `
  --business-year 2025 `
  --candle-count 100 `
  --history-years 3 `
  --macro-lookback-days 31 `
  --disclosure-lookback-days 365 `
  --output data/private/live-research
```

## Data boundaries

- Market prices remain TossInvest read-only data.
- Financial, disclosure, and share-count evidence remains OpenDART data.
- Macro evidence remains Bank of Korea ECOS data.
- The public-IP diagnostic is used only after a TossInvest allowlist rejection.
- No account balance, position, order, or trade-submission endpoint is called.
- The valuation layer still uses reported results rather than analyst consensus or target prices.
