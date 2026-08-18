# SK hynix company-GP ex-ante estimator freeze v1

## Purpose

The lagged-filing PIT certification closes 14 target-blind development rows and 70 PIT-eligible
feature observations. The next step is **not** to join historical GP targets immediately. The
candidate estimators and chronological selection rule must first be fixed without seeing any
historical backtest performance.

This freeze was committed before any target join or historical backtest runner was added.
2026Q1 remains contaminated/report-only and 2026Q3 remains unread and unevaluated.

## Frozen first-round candidates

The first round deliberately uses a nested, low-dimensional OLS sequence:

1. `lagged_gp_affine_ols`
   - intercept + lagged company GP;
   - `p=2`, including the intercept.
2. `lagged_gp_nand_mix_ols`
   - intercept + lagged company GP + lagged NAND revenue share;
   - `p=3`.
3. `lagged_gp_full_mix_ols`
   - intercept + lagged company GP + lagged NAND share + lagged Other share;
   - `p=4`.

The coefficients are empirical prediction weights only. They are not product margins,
structural elasticities, or source facts.

Lagged company revenue and lagged gross margin remain present in the certified five-feature
bundle but are intentionally not added to this first candidate sequence. This avoids expanding
parameter count before the first target join. The V5 bridge architecture is also excluded from
this first round because the five-feature PIT bundle does not contain the same-quarter cycle
inputs used by V5.

## Sample heuristic

For a fitted candidate with `p` parameters, including the intercept, the frozen heuristic is:

`minimum training rows = max(2p, p + 8)`

This is explicitly a heuristic, not a statistical theorem.

The three candidates therefore require 10, 11, and 12 training rows respectively. The
historical protocol separately requires at least eight scored chronological folds.

Candidate MAEs must be compared on the **same** folds, so the first scored fold is shared across
all candidates and begins only after 12 training rows. Eight common scored folds therefore
require:

`12 initial training rows + 8 scored rows = 20 complete target-blind feature rows`

The currently certified bundle has 14 rows. It is therefore six rows short of the frozen first
join requirement.

## Why the 14-row backtest is not run

With 14 rows, starting after 12 training rows would produce only two common scored folds. Starting
earlier to manufacture eight folds would violate the sample heuristic for one or more frozen
candidates. Running only the smallest candidate now and adding the other candidates later would
also let target performance influence candidate availability.

The fail-closed action is therefore to keep `target_join_allowed=false` and
`estimator_fit_allowed=false` until the target-blind PIT development panel is expanded to at
least 20 complete rows under a separately versioned period/source contract.

## Frozen chronological selection rule

When the sample gate is eventually satisfied:

- use chronological expanding-window evaluation only;
- use one identical set of eight scored folds for every candidate and the benchmark;
- fit predictor centering/scaling from each training fold only;
- require full design-matrix column rank in every scored fold;
- require positive residual degrees of freedom in every scored fold;
- report condition number and coefficient stability without adding a post-hoc threshold;
- use aggregate MAE in KRW million as the primary metric;
- require a candidate to strictly beat the frozen previous-quarter GP persistence benchmark;
- among passing candidates, select the lowest MAE;
- on an exact MAE tie, prefer lower parameter count, then earlier manifest order;
- if no candidate passes, select no estimator and keep forward forecasting disabled.

Hyperparameter tuning, adding candidates, changing feature subsets, or changing scored folds
after the first target join is prohibited.

## Current scientific conclusion

The 14-row / 70-observation PIT certification is a successful source and timing result, but it
is **not yet enough sample depth for the already-frozen first estimator comparison**. The next
step is therefore target-blind source expansion, not a premature historical backtest.
