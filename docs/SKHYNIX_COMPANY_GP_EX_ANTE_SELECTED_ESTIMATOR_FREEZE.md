# SK hynix company-GP ex-ante selected-estimator freeze

## Historical selection result

The first locked twenty-period chronological evaluation completed on 2026-08-21 without
opening the protected 2026Q3 outcome boundary.

The preregistered persistence benchmark produced MAE `1,677,703.75` KRW million. The only
candidate that strictly beat that benchmark was `lagged_gp_affine_ols`, with MAE
`1,249,345.1117558964` KRW million, a relative MAE reduction of about 25.5%. It beat the
benchmark on seven of the eight scored chronological folds; the exception was 2022Q3.
The NAND-mix and full-mix candidates did not beat the frozen benchmark and therefore cannot
be selected in this research round.

Historical evidence bindings from that run:

- schema-repair / execution evidence: `5382b27f0d38f8c9308a0cec1f5adbdb64e6dd79112d840984aa9f90fff1eedf`
- scope evidence: `03f25597552371b2c1cd48812e2b3ce1144d6d6c685807a43d9a3b08cf402ffe`
- raw target capture evidence: `ab05ff3f365933653490b6d32838713a7e14c719693d6f67e608cb28b9909571`
- target join evidence: `44915cb9fcec00252c2efe1888a2653e9a8a83c05af7a7a47026ef08972fe534`
- backtest evidence: `478ef67e2470f72e7e5a96cd469e5bc3152dc3e6e0574fcd1437603822242014`
- pre-target estimator freeze evidence: `f7000f312a698a90ec5b16b6eb05e5b18e42462e0d9f0d7bdef83567c8a82ebc`

These are observed-run provenance facts, not new model choices.

## What this stage may do

This stage may only inherit the selected candidate from the frozen historical backtest and
refit that exact candidate on all twenty locked historical rows. The estimator remains OLS;
the selected predictor set comes from the pre-target estimator freeze. Predictor centering
and scaling are fit on all twenty training rows with population standard deviation (`ddof=0`),
matching the previously frozen preprocessing semantics.

The artifact records:

- every upstream evidence binding,
- the selected candidate id and predictors,
- all twenty training periods,
- predictor means and scales,
- standardized OLS coefficients,
- equivalent raw-unit intercept and slopes,
- design rank and residual degrees of freedom,
- condition number as a report-only diagnostic,
- in-sample MAE/RMSE as report-only diagnostics,
- the historical benchmark and selected-candidate OOS MAEs.

## What this stage may not do

It cannot add candidates, change predictors, add features, tune hyperparameters, change the
benchmark, rescore folds, or use the historical result to redesign the model. It also cannot
read or evaluate 2026Q3, and it does not yet produce a numeric forward forecast.

After the selected-estimator artifact is locked, the next permitted stage is to freeze the
2026Q3 prospective feature vector from information available at the forecast origin while
keeping the 2026Q3 realized target sealed.
