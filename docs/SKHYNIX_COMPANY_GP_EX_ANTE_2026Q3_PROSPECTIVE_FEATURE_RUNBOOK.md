# 2026Q3 prospective feature freeze runbook

After the merge, pull `main` and run the feature freeze before the frozen 2026Q3 forecast
origin (`2026-08-31 23:59:59 Asia/Seoul`):

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"

git switch main
git pull --ff-only origin main

$prospectiveFeatureJson = & ".\.venv\Scripts\python.exe" `
    -m alpha_cycle.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature_cli |
    Out-String

$prospectiveFeatureJson
```

Expected first-run properties:

- `raw_source_capture_reused: false`
- `feature_vector_reused: false`
- `target_period: 2026Q3`
- `source_period: 2026Q2`
- `predictors` contains only `lagged_company_gross_profit`
- `prospective_feature_vector_frozen: true`
- `prospective_forecast_run: false`
- all 2026Q3 target/source-outcome/evaluation flags remain `false`
- `numeric_forward_forecast_enabled: false`

A repeat run must replay the locked raw bytes and feature vector, reporting both reuse flags
as `true`. Do not delete the private source-capture or feature-vector artifacts.

A successful first freeze ends with:

`run_locked_2026q3_numeric_forecast_without_reading_2026q3_outcome`
