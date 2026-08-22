# SK hynix 2026Q3 prospective outcome scoring preregistration

## Why freeze the scorer now

The 2026Q3 company-gross-profit forecast is already locked before its 2026-08-31 forecast
origin. The selected forecast is `73,030,702.00644387` KRW million and the frozen persistence
benchmark is `65,991,356.0` KRW million. The protected 2026Q3 outcome has not been read.

The remaining methodological degree of freedom is how the future outcome will be scored.
This file freezes that rule before the outcome exists so the research round cannot choose a
favorable metric, tolerance, target source, or benchmark after seeing the result.

## Frozen target source

The eventual actual is the 2026Q3 company gross profit from OpenDART `fnlttSinglAcntAll`:

- business year: 2026
- report code: `11014`
- financial statement division: `CFS`
- amount field: `thstrm_amount`
- statement rows: `IS` or `CIS`
- standard account aliases: inherited exactly from historical execution v2
- revenue, cost of sales, and gross profit must come from the same filing receipt
- `Revenue - Cost of Sales = Gross Profit` must hold exactly

There is no fuzzy account-name matching, arithmetic reconstruction of a missing source
account, alternate source fallback, correction selection, or partial target acceptance.

The first non-empty official payload is content-addressed and locked before account value
extraction. Once a successful source capture exists, the scorer cannot refresh it.

## Frozen score

The primary prospective metric is one-point absolute error in KRW million.

For actual `A`, selected forecast `S`, and persistence benchmark `B`:

- selected signed error = `S - A`
- benchmark signed error = `B - A`
- selected absolute error = `abs(S - A)`
- benchmark absolute error = `abs(B - A)`
- absolute-error advantage = `benchmark_abs_error - selected_abs_error`

The selected model wins only when its absolute error is strictly lower than the benchmark's.
Exact equality is a tie. There is no tolerance-based tie and historical MAE is not converted
into a prospective pass/fail threshold.

## Timing and boundary

Outcome acquisition is prohibited before the 2026Q3 period end, 2026-09-30. The CLI also
requires an explicit evaluation date. In practice, do not run the scoring CLI until the
official 2026Q3 quarterly filing is available in OpenDART.

If the endpoint returns no financial rows, the run fails and persists nothing. A successful
score is immutable and records that the protected boundary was crossed for the first time:

- `2026q3_target_read = true`
- `2026q3_source_outcome_loaded = true`
- `2026q3_evaluated = true`
- `model_refit_run = false`
- `forecast_changed_after_lock = false`

Scoring cannot refit the model, alter coefficients or predictors, change the benchmark, or
rewrite the frozen forecast. Investment-action outputs remain outside this scorer.

## Future command — do not run yet

After the official 2026Q3 quarterly filing exists, use an evaluation date on or after its
receipt date:

```powershell
$scoreJson = & ".\.venv\Scripts\python.exe" `
    -m alpha_cycle.sk_hynix_company_gp_ex_ante_2026q3_outcome_scoring_cli `
    --evaluation-date YYYY-MM-DD |
    Out-String

$scoreJson
```

Until then, the correct scientific action is to leave the model, feature vector, numeric
forecast, benchmark, and scoring contract unchanged.
