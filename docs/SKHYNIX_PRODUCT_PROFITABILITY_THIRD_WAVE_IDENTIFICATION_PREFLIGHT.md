# SK hynix third-wave identification preflight

## Why this stage exists

The frozen v2 bounded logit-margin model solved the accounting hard-bound problem by forcing
component margins into `(0, 1)`, but the first development fit was not structurally identified:
its fitted Jacobian had rank 5 for seven parameters and several leave-one-out fits also lost
rank or convergence. That failure does not justify changing damping, adding regularization, or
reducing parameters after seeing the result without another explicit research stage.

The next stage therefore expands source coverage before any replacement estimator is fit.

## Third-wave source frontier

The registered third wave is 2017Q1-2018Q3, Q1-Q3 only. Each row already has four exact
issuer driver facts from SK hynix Newsroom. OpenDART product revenue and company profitability
must still be independently acquired and exactly reconciled.

The preserved product-table recovery path now explicitly supports 2017Q1-2020Q3 Q1-Q3 while
continuing to forbid Q4. A direct parser success is also accepted, but only after the
certification JSON, filing receipt, product/company revenue identity, archived ZIP hash, and
source trust flags are reverified.

## Two identification panels

Once all six third-wave rows are source-complete, the preflight builds two panels:

1. `clean_historical_21`: the original 15 v1 training rows plus the six 2017-2018 rows. The
   already-spent 2026Q1 outcome is excluded.
2. `contaminated_development_22`: the same 21 rows plus 2026Q1, explicitly marked as
   outcome-seen development data.

Both panels use the common seven-column direction-regime design:

- DRAM revenue
- DRAM revenue x ASP direction sign
- DRAM revenue x bit-volume direction sign
- NAND revenue
- NAND revenue x ASP direction sign
- NAND revenue x bit-volume direction sign
- Other revenue

## Gate

The preflight can become ready for **new-method registration** only when:

- all six third-wave source layers are certified;
- every company/product revenue identity reconciles; and
- both the 21-row clean panel and 22-row contaminated-development panel have rank 7.

Normalized condition number, regime coverage, and DRAM/NAND/Other revenue-share ranges are
reported only. No post-hoc cutoff is created from the failed v2 result.

A green preflight still does **not** fit a model. A replacement estimator must be separately
pre-registered before any coefficient or fit metric is observed.

## Holdout boundary

- 2026Q1 remains spent and cannot become unseen again.
- 2026Q2 is not claimed as untouched.
- 2026Q3 remains the reserved future holdout.
- This preflight has no 2026Q3 loading or scoring path.
