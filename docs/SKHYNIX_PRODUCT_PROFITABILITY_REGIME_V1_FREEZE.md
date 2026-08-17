# SK hynix product-profitability regime v1 freeze

The 15-row source panel passed the pre-estimation source, reconciliation, sample-depth, and
rank gates before this method was registered. At freeze time, the 15x7 design rank and
normalized condition number had been inspected; coefficient values, training-fit metrics,
and the 2026Q1 holdout score had not been inspected.

## Frozen primary estimator

- Training: 2019Q1-2020Q3 and 2023Q1-2025Q3 (15 direct-quarter rows).
- Holdout: 2026Q1, excluded from training.
- Driver semantics: categorical issuer direction regime `Increase=+1`, `Flat=0`,
  `Decrease=-1`.
- The exact numeric 2019-2020 ASP/bit values remain source facts, but their magnitudes are not
  used by v1. They are downcast to direction so all 15 rows share one estimator semantics.
- Estimator: seven-term OLS without a global intercept.
- Coefficients are model outputs, not direct product-margin source facts or elasticities to a
  one-percentage-point driver move.

## Training gate

The frozen v1 may score the holdout only if all of the following are true:

1. exactly 15 training rows and seven parameters;
2. at least eight residual degrees of freedom;
3. full column rank;
4. company/product revenue reconciliation within KRW 1 million;
5. every leave-one-out training fold remains full rank; and
6. leave-one-out model MAE is strictly lower than a leave-one-out mean-gross-margin benchmark.

Cook's distance and jackknife coefficient sign stability are reported as diagnostics only;
they are not post-hoc pass/fail thresholds.

## Holdout protocol

If the training gate passes, 2026Q1 is scored once. The frozen model absolute error must be
strictly lower than the pre-registered training-mean-gross-margin benchmark error. The result
is persisted immutably. Re-running the same validation must reuse that result. Frozen v1 may
not be refit to 2026Q1 after exposure, regardless of whether the holdout passes or fails.

A successful holdout does not by itself enable a forward numeric forecast, fair value, target
price, or decision score. Those require a separate forward-input and plausibility contract.
