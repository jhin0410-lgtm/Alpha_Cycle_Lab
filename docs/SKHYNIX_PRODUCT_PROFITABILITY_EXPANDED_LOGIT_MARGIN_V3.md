# SK hynix product profitability expanded logit-margin V3

## Purpose

V2 solved the hard accounting-bound problem by constraining product margins through a logistic link, but its 16-row development fit was not identifiable enough for structural use: the fitted nonlinear Jacobian lost column rank and several product-margin directions saturated.

After that outcome was observed, six additional issuer-source quarters from 2017Q1 through 2018Q3 were acquired and source-closed.  Before any replacement fit, the expanded direction-design preflight showed that both the clean historical panel and the panel including already-seen 2026Q1 development data had all seven algebraic design columns available.

V3 is the preregistered test of whether the original bounded seven-parameter economic family becomes estimable once those additional clean historical regimes are included.  It deliberately does **not** reduce parameters or add regularization before this comparison is run.

## Frozen training panel

V3 estimation uses exactly 21 clean historical rows:

- 2017Q1, 2017Q2, 2017Q3
- 2018Q1, 2018Q2, 2018Q3
- 2019Q1, 2019Q2, 2019Q3
- 2020Q1, 2020Q2, 2020Q3
- 2023Q1, 2023Q2, 2023Q3
- 2024Q1, 2024Q2, 2024Q3
- 2025Q1, 2025Q2, 2025Q3

The six 2017-2018 rows use exact issuer numeric driver facts only to determine the preregistered categorical sign regime. Numeric magnitude is retained as source evidence but is not used in the V3 fit.

## Contamination boundary

2026Q1 was already observed during V1/V2 work.  V3 therefore treats 2026Q1 only as a retrospective contaminated stress diagnostic.

It is not:

- a V3 training row;
- a V3 LOOCV row;
- a V3 model-selection gate;
- an independent validation observation.

2026Q2 is not claimed as untouched.  2026Q3 remains the reserved future untouched holdout and is not loaded or evaluated by the V3 fitter.

## Structural equation

V3 keeps the V2 bounded family unchanged:

```text
dram_score = theta0 + theta1 * dram_asp_sign + theta2 * dram_bit_sign
nand_score = theta3 + theta4 * nand_asp_sign + theta5 * nand_bit_sign

dram_margin = sigmoid(dram_score)
nand_margin = sigmoid(nand_score)
other_margin = sigmoid(theta6)

company_gross_profit =
    dram_revenue * dram_margin
  + nand_revenue * nand_margin
  + other_revenue * other_margin
```

The seven coefficients are model parameters. They are not direct source facts and are not literal percentage sensitivities to reported ASP or bit-shipment magnitudes.

## Prefit identification gate

Before the nonlinear solver is called, V3 requires:

1. exactly 21 training rows;
2. seven parameters;
3. at least 14 residual degrees of freedom;
4. full rank of the seven-column revenue-weighted direction design;
5. full rank of that design after each single training row is removed.

The normalized design condition number and each leave-one-out condition number are reported only. No condition-number cutoff was invented after seeing the earlier V2 failure.

If the prefit gate fails, the V3 solver is not called.

## Development validation gate

After a prefit pass, V3 requires all of the following on the 21-row clean panel:

- deterministic optimizer convergence;
- full nonlinear Jacobian column rank;
- convergence of every leave-one-out nonlinear fit;
- full nonlinear Jacobian rank in every leave-one-out fit;
- mean LOOCV absolute error strictly below the same leave-one-out mean-gross-margin-scaled-revenue benchmark used previously;
- component margins inside the structural `(0, 1)` logistic bounds.

Jacobian condition number and coefficient jackknife stability are report-only diagnostics.  The already-seen 2026Q1 stress result is also report-only and cannot make the gate pass or fail.

## Solver freeze

The deterministic damped Gauss-Newton solver contract is kept identical to V2 for comparability:

- mean company revenue scaling;
- training mean gross-margin logit initialization;
- zero direction effects at initialization;
- diagonal `J'J` damping with the same fixed floor and damping schedule;
- the same iteration, rejected-step, step-tolerance, and relative-SSE stopping rules.

This avoids changing both the data and the optimizer at the same time.

## Interpretation of the next result

A V3 gate pass would show that the bounded seven-parameter family is estimable and cross-validates better than the preregistered benchmark on the expanded clean panel. It would **not** by itself authorize a price target, investment decision score, or structural margin truth claim.

A V3 failure would be equally informative. In particular:

- prefit rank failure would indicate remaining structural aliasing in the expanded direction design;
- nonlinear Jacobian rank loss or unstable jackknife behavior would indicate weak nonlinear identification or saturation despite algebraic rank;
- LOOCV benchmark failure would indicate insufficient predictive value even if identification succeeds.

Only after that result is known should a lower-dimensional or regularized successor be considered, and any such successor must be a new frozen method version rather than a tuned V3 rerun.
