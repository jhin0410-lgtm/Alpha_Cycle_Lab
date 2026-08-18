# SK hynix V3 nonlinear nullspace diagnostic

V3 restored the seven-column **prefit direction design** to full rank on the clean 21-row panel, but the fitted bounded-logit Jacobian remained rank deficient. This diagnostic separates those two facts instead of treating prefit rank as proof of nonlinear identification.

The diagnostic consumes only the already-written private V3 fit report. It recomputes the full and leave-one-out Jacobians, verifies stored rank results, reports normalized singular values and the smallest right-singular-vector loadings, and reports the rank/condition geometry after deleting each single parameter.

All outputs are report-only. The diagnostic does **not** refit V3, choose a reduced model, tune a regularizer, open a forecast or valuation path, or load/evaluate 2026Q3. A replacement method must be registered separately after the diagnostic is inspected.

Run:

```powershell
$python -m alpha_cycle.sk_hynix_product_profitability_v3_nullspace_cli
```

The most decision-relevant fields are:

- `dominant_nullspace_direction_report_only`
- `parameter_deletion_diagnostics_report_only`
- `rank_deficient_loocv_fold_count`
- `rank_deficient_loocv_periods`
- `loocv_diagnostics_report_only`
- `nonlinear_rank_loss_after_link_fit`

No condition-number threshold is introduced after seeing V3. Condition numbers and singular-value ratios remain descriptive diagnostics only.
