# Selected-estimator freeze runbook

After pulling the merge that adds the full-20 selected-estimator freeze, run:

```powershell
cd "C:\Download\쿠쿠\coding\Alpha_Cycle_Lab"

$selectedEstimatorJson = & ".\.venv\Scripts\python.exe" `
    -m alpha_cycle.sk_hynix_company_gp_ex_ante_selected_estimator_freeze_cli |
    Out-String

$selectedEstimatorJson
```

Expected first-run properties:

- `artifact_reused` is `false`.
- `selected_candidate_id` matches the already frozen historical backtest selection.
- `training_row_count` is exactly `20`.
- `design_rank` equals `parameter_count`.
- `residual_degrees_of_freedom` is positive.
- `2026q3_target_read`, `2026q3_source_outcome_loaded`, and `2026q3_evaluated` remain `false`.
- `numeric_forward_forecast_enabled` remains `false`.

A successful run ends with:

`freeze_2026q3_prospective_feature_vector_without_reading_2026q3_outcome`

Do not delete or rewrite the selected-estimator artifact after it is created. A repeat run
must reproduce the same evidence and report `artifact_reused: true`.
