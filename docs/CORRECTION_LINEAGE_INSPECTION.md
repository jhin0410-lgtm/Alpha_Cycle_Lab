# Correction disclosure lineage inspection

Use the dedicated command instead of manually reading `latest_run.json` and joining paths in PowerShell.

```powershell
.\scripts\show_latest_corrections.cmd
```

The command reads `data/private/live-research/latest_run.json` as UTF-8, resolves the latest decision directory, and loads `disclosure_events.csv` directly. This avoids Windows PowerShell 5.1 path corruption when the repository path contains Korean characters.

## Filters

Show one company:

```powershell
.\scripts\show_latest_corrections.cmd --ticker 000660
```

Show only the newest event in each correction chain:

```powershell
.\scripts\show_latest_corrections.cmd --only-latest
```

Produce JSON or CSV instead of a console table:

```powershell
.\scripts\show_latest_corrections.cmd --format json
.\scripts\show_latest_corrections.cmd --format csv
```

Use a non-default pipeline status file:

```powershell
.\scripts\show_latest_corrections.cmd --status C:\path\to\latest_run.json
```

## Output fields

- `ticker`
- `receipt_date`
- `report_name`
- `correction_parent_rcept_no`
- `correction_chain_root_rcept_no`
- `correction_chain_order`
- `correction_lineage_status`
- `is_latest_in_correction_chain`

The command is evidence-only. It does not interpret whether a correction is positive, negative, or immaterial.
