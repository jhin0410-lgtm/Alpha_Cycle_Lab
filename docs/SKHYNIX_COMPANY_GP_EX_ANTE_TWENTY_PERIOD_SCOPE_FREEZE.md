# SK hynix company-GP ex-ante twenty-period scope freeze

## Purpose

The PIT panel expansion now reaches the preregistered 20-row sample gate without reading any historical target value. Before the first target join, the exact development sample must be frozen so later model results cannot change which periods or features enter the comparison.

This layer does **not** rewrite the original forecast protocol. The original protocol remains the preregistration record that defined the forecast-origin rule and earlier development intent. The scope-freeze artifact records the empirically source-certifiable historical panel that is actually allowed to enter the first target join.

## Exact frozen historical scope

The only target periods admitted by this freeze are Q2 and Q3 for every year from 2016 through 2025:

- 2016Q2, 2016Q3
- 2017Q2, 2017Q3
- 2018Q2, 2018Q3
- 2019Q2, 2019Q3
- 2020Q2, 2020Q3
- 2021Q2, 2021Q3
- 2022Q2, 2022Q3
- 2023Q2, 2023Q3
- 2024Q2, 2024Q3
- 2025Q2, 2025Q3

Each row must contain exactly these five PIT features:

1. `lagged_company_revenue`
2. `lagged_company_gross_profit`
3. `lagged_company_gross_margin`
4. `lagged_nand_revenue_share`
5. `lagged_other_revenue_share`

The completed geometry is therefore 20 target rows and 100 target-blind feature observations.

## What is bound

The freeze binds all of the following before target access:

- frozen forecast-protocol evidence identity
- frozen feature-frontier evidence identity
- frozen estimator-selection evidence identity
- PIT expansion-contract evidence identity
- SHA-256 of the exact successful expansion report
- base PIT bundle evidence identity
- completed 20-row PIT bundle evidence identity
- exact 20 target-period IDs and five-feature schema
- selected legacy source year (`2016`)
- chronological estimator geometry: 12 initial training rows plus 8 scored folds
- successful sample eligibility of every preregistered estimator candidate

The freeze also re-audits every feature observation directly against the frozen forecast-origin timing rule and feature-provenance policy. The added 2016, 2021, and 2022 periods are therefore admitted only through this explicit refrozen scope; they are not silently treated as if they had been in the original development-period list.

## Trust boundary

Creating this artifact must leave all of these states false:

- historical target values read
- target join authorized
- estimator fit authorized
- historical backtest run
- 2026Q3 target read
- 2026Q3 source outcome loaded

The freeze is a prerequisite for the next stage; it is not itself permission to read targets.

## Run after a successful PIT expansion

From the repository root:

```powershell
$freezeJson = & ".\.venv\Scripts\python.exe" `
    -m alpha_cycle.sk_hynix_company_gp_ex_ante_scope_freeze_cli |
    Out-String

$freezeJson
```

The default inputs are the successful expansion outputs:

- `data/private/research/skhynix-company-gp-ex-ante-pit-panel-expansion/latest_expansion_report.json`
- `data/private/research/skhynix-company-gp-ex-ante-pit-panel-expansion/latest_combined_feature_bundle.json`

The default output is:

- `data/private/research/skhynix-company-gp-ex-ante-scope-freeze/latest_scope_freeze.json`

A hash-named immutable copy is written beside the latest pointer as `scope-<evidence_id>.json`.

## Completion condition

A successful run reports:

- `target_row_count: 20`
- `feature_observation_count: 100`
- `selected_legacy_year: 2016`
- `scored_fold_count: 8`
- `all_observations_point_in_time_eligible: true`
- `all_frozen_candidates_sample_eligible: true`
- all target/join/fit/backtest/Q3 trust flags still `false`
- `next_action: perform_first_historical_target_join_against_exact_frozen_scope`

Only after this artifact exists and replays exactly should the first historical company-GP target join be implemented.
