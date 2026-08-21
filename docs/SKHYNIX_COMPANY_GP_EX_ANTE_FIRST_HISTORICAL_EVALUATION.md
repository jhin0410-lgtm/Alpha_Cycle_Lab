# SK hynix ex-ante first historical target join and backtest

## Purpose

This stage is the first intentional crossing of the historical company-gross-profit target
boundary. It is allowed only after the exact twenty-period PIT scope has been frozen.

The execution contract is committed before any target is read. It fixes:

- exact rows: 2016Q2/Q3 through 2025Q2/Q3, twenty rows total;
- target metric: consolidated company gross profit, KRW million;
- source: official OpenDART `fnlttSinglAcntAll`;
- Q2 report code `11012`, Q3 report code `11014`;
- current-term field `thstrm_amount`;
- Revenue, Cost of Sales, and Gross Profit account identities;
- no correction search/selection, fallback, partial join, or post-join target refresh;
- predictor centering/scaling from each training fold only, population standard deviation
  (`ddof=0`), and no target standardization;
- twelve initial chronological training rows and eight expanding-window scored folds;
- persistence benchmark = the frozen `lagged_company_gross_profit` feature;
- all three candidates and their order from the existing estimator freeze;
- strict benchmark beat requirement and the preregistered tie-breaking order.

## Target definition and archival

The first run requests only the twenty frozen historical target periods. Each target row must
resolve Revenue, Cost of Sales, and Gross Profit to one filing receipt and must satisfy the
direct accounting identity `Revenue - Cost of Sales = Gross Profit`.

The decoded official OpenDART response is serialized deterministically and the captured bytes
are SHA-256 bound. The first complete target join is then stored under a content-addressed
artifact directory. Once `latest_historical_target_join.json` exists, a different target join
cannot replace it. Later runs replay the locked target artifact instead of refreshing targets.

This is deliberate: later corrections or source changes must not silently change the outcome
sample after model performance has been observed.

## Chronological evaluation

Rows are ordered exactly as frozen in the scope. For scored fold 1, rows 1-12 train and row 13
is scored. The window then expands by one row until fold 8 trains on rows 1-19 and scores row
20.

For each candidate and each fold:

1. take only the candidate predictors frozen in the estimator manifest;
2. estimate predictor means and standard deviations from the training rows only;
3. reject a fold with a zero/non-finite predictor scale;
4. add the intercept after standardization;
5. require full design column rank and positive residual degrees of freedom;
6. fit ordinary least squares with no tuning;
7. transform the held-out row using training-fold statistics only;
8. score absolute error in KRW million.

Condition number and standardized-coefficient drift are reported, not used as hidden selection
thresholds.

A candidate must have all eight valid folds and aggregate MAE strictly below the persistence
benchmark. Among passing candidates, selection follows the frozen order:

1. lowest aggregate chronological MAE;
2. lower parameter count on an exact MAE tie;
3. earlier estimator-freeze manifest order on any remaining exact tie.

If none passes, no estimator is selected and numeric forward forecasting remains disabled.

## Protected outcomes

This execution does not load or score:

- 2026Q1 for candidate selection;
- 2026Q3 target or source outcome;
- 2026Q4 target.

Even if a historical candidate is selected, this stage does not enable a prospective numeric
forecast. A selected estimator must be frozen in a subsequent, separate stage before any
protected prospective evaluation.

## Operator command

After this code is merged and the local exact-20 scope freeze exists:

```powershell
$evaluationJson = & ".\.venv\Scripts\python.exe" `
    -m alpha_cycle.sk_hynix_company_gp_ex_ante_historical_evaluation_cli `
    --evaluation-date 2026-08-21 |
    Out-String

$evaluationJson
```

The first successful run locks the historical target artifact and performs the frozen
backtest. Subsequent runs replay the locked target values rather than querying updated target
values.
