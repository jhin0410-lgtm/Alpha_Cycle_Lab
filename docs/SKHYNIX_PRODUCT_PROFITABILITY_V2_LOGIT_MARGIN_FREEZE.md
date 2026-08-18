# SK hynix product-profitability v2 bounded-margin freeze

## Why v2 exists

Frozen v1 passed its pre-registered training and 2026Q1 predictive holdout gates, but a
post-holdout accounting audit showed that treating its linear coefficient combinations as
literal product gross margins can imply more than 100% gross margin. v1 therefore remains a
validated empirical regime predictor only.

v2 changes the structural parameterization before fitting. DRAM, NAND, and Other margins are
produced through logistic links, so every component margin is structurally inside `(0, 1)`.
The company gross-profit estimate is the sum of product revenue multiplied by these bounded
component margins.

## Development/holdout boundary

- The original 15 v1 training rows remain development data.
- 2026Q1 was already exposed as the v1 holdout and is explicitly reused only as contaminated
  v2 development data.
- 2026Q2 is not claimed as an untouched holdout because its public earnings are already known.
- 2026Q3 is reserved as the next future untouched holdout.
- The v2 development fitter contains no 2026Q3 loader or scoring path.

## Frozen solver

v2 uses a deterministic damped Gauss-Newton solver implemented with NumPy only. The solver,
initialization, common revenue scaling, damping update rule, iteration limits, and convergence
tolerances are frozen before v2 coefficients or fit metrics are inspected.

## Development gate

The development gate requires 16 rows, seven parameters, at least nine residual degrees of
freedom, optimizer convergence, full Jacobian rank, all leave-one-out folds converged and full
rank, LOOCV MAE below the same gross-margin benchmark family used previously, and component
margins inside `(0, 1)` by construction.

Passing the development gate does not open a forecast, fair value, target price, decision
score, or the 2026Q3 holdout. Those remain separate future contracts.
