# SK hynix company-GP empirical V5

## Why the model family changed

The product-margin structural development branch is closed for the current source panel.
The source-side direction designs were algebraically identifiable after the 2017-2018
third-wave expansion, but repeated bounded-logit development fits still lost nonlinear
Jacobian rank through component-margin saturation. The V4 local private development report
confirmed that reducing the parameter count inside the same product-margin link did not
resolve that failure mode.

This is not treated as evidence that a real product margin is zero. It is evidence that the
available company-level gross-profit target, product revenue mix, and direction-only cycle
inputs do not identify the requested product-margin decomposition under the tested link.

## V5 scope

V5 stops estimating product margins. It directly models company gross profit with a frozen
seven-column empirical design:

1. company revenue,
2. company revenue x DRAM ASP direction,
3. company revenue x DRAM bit-volume direction,
4. company revenue x NAND ASP direction,
5. company revenue x NAND bit-volume direction,
6. NAND revenue,
7. Other revenue.

The direction inputs remain categorical `-1 / 0 / +1`. Exact numeric driver magnitudes are
retained as source facts where available but are not mixed into the fit because that semantic
coverage is not uniform across all 21 training rows.

## Interpretation boundary

V5 coefficients are empirical company-GP weights. They are not:

- literal DRAM or NAND margins,
- literal ASP elasticities,
- literal bit-volume elasticities,
- a source-backed allocation of company gross profit to products.

No V5 output may reopen product-margin structural interpretation.

## Frozen panel and validation

Training uses the clean 21-row historical panel only. The already-observed 2026Q1 result is
retrospective contaminated stress data and cannot affect fitting or the model-selection gate.
The same leave-one-out mean-company-gross-margin benchmark is retained.

The development gate requires:

- 21 rows and 7 parameters,
- full design rank,
- full design rank after every one-row deletion,
- full rank in every LOOCV fit,
- LOOCV gross-profit MAE strictly better than the unchanged benchmark.

Condition numbers and coefficient jackknife stability are report-only; no post-outcome cutoff
is introduced.

## Future holdout

2026Q3 remains sealed. Passing V5 development does not authorize loading or evaluating Q3,
and it does not enable forward forecasts, valuation, target prices, or decision scores. A
separately frozen future-holdout protocol is required.
