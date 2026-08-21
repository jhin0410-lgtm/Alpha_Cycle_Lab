# SK hynix ex-ante company GP: first historical target schema incident

## Incident

The first local execution of the frozen historical evaluation was run from
`main@13cd1a73ffed6f3927e3acaf9b2aa0d2db5cebb9` on 2026-08-21.

The process failed at the first target observation, `2016Q2`, with:

```text
Historical target account must resolve uniquely: 2016 report_code=11012 label=revenue count=0
```

The failure occurred because execution v1 accepted only newer `ifrs-full_*` revenue concept
IDs. Historical IFRS XBRL filings can use the legacy `ifrs_*` namespace for the same standard
concept family.

## What crossed the boundary

The v1 implementation calls `collect_historical_target_payloads()` for all twenty frozen
periods before `build_historical_target_join()` starts target extraction. Therefore the first
attempt retrieved the twenty official OpenDART payloads into process memory before the
2016Q2 extraction exception occurred.

This fact must not be hidden or relabeled as a pristine pre-target-read state.

However, the failed attempt did **not**:

- construct a `HistoricalTargetObservation`;
- persist a historical target join;
- fit any estimator;
- run the chronological backtest;
- select a candidate;
- read or evaluate protected 2026Q3/2026Q4 outcomes.

No target values from the failed payloads were printed in the local traceback or used to
choose the v2 repair.

## V2 repair boundary

Execution v2 is intentionally described as
`frozen_after_schema_failure_before_target_resolution`, not as
`frozen_pre_first_target_read`.

The only source-selection change is a fixed XBRL standard-account namespace alias expansion:

- revenue: `ifrs_Revenue`, `ifrs-full_Revenue`,
  `ifrs-full_RevenueFromContractsWithCustomers`;
- cost of sales: `ifrs_CostOfSales`, `ifrs-full_CostOfSales`;
- gross profit: `ifrs_GrossProfit`, `ifrs-full_GrossProfit`.

No fuzzy account-name matching, arithmetic reconstruction of a missing source account,
correction search, source fallback, partial target join, or post-join target refresh is
allowed.

The exact twenty target periods, five PIT features, three OLS candidates, 12-row initial
training window, eight scored folds, persistence benchmark, MAE metric, preprocessing, and
selection rule remain identical to execution v1.

## Raw capture repair

V2 changes the execution order so raw OpenDART payload bytes are persisted under an immutable
SHA-256-bound capture **before** target extraction. If a later parser/schema error occurs,
subsequent code must replay the already locked bytes rather than query a refreshed target
response.

This closes the provenance gap exposed by v1, where payloads had been retrieved but were lost
when extraction failed before persistence.

## External schema basis

OpenDART documents `account_id` as the XBRL standard account ID and documents
`thstrm_amount` as the three-month amount for quarterly/semiannual income statements. IFRS
taxonomy materials also document the coexistence/version transition between legacy
`ifrs_*` and newer `ifrs-full_*` namespace concepts. The v2 alias expansion is therefore a
schema-compatibility repair, not a result-conditioned model change.
