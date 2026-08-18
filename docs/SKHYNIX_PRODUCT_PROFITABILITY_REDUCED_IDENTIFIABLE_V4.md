# SK hynix product profitability V4: reduced identifiable bounded model

V4 is registered only after V3's nonlinear identification failure was observed and decomposed.
It is a new method version, not a retuned V3.

## Why the model is reduced

The V3 source panel was algebraically full rank before fitting, including every leave-one-out
direction design. After the bounded logistic link was fitted, however, the nonlinear Jacobian
lost rank. The diagnostic showed two distinct pathologies: the independent Other-margin
sensitivity collapsed to essentially zero, while the dominant normalized null direction was
shared by the NAND intercept and NAND bit-volume effect. Therefore V4 removes both degrees
of freedom that cannot be defended as independently identified.

## Frozen five-parameter structure

V4 keeps three DRAM terms and two NAND terms:

- DRAM logit intercept
- DRAM ASP-direction effect
- DRAM bit-volume-direction effect
- NAND logit intercept
- NAND ASP-direction effect

NAND bit-volume direction is not used in the fitted NAND score. Other revenue is not assigned
to DRAM or NAND and no synthetic Other margin is created. The model simply does not estimate
an independent Other contribution; any such contribution remains inside the company-level
gross-profit residual. This is **not** a claim that the true Other margin is zero.

The fitted equation is:

`GP_hat = DRAM_revenue * sigmoid(DRAM_score) + NAND_revenue * sigmoid(NAND_score)`

where the two scores use only the frozen terms above. Coefficients and implied modeled margins
remain model outputs, not issuer source facts or literal product-margin disclosures.

## Data roles

- Clean estimation and LOOCV panel: 2017Q1-2018Q3 plus the original V1 fifteen rows (21 total).
- 2026Q1: already observed; retrospective contaminated stress report only.
- 2026Q2: not claimed as untouched.
- 2026Q3: reserved untouched future holdout and not loaded by the V4 fitter.

## Gates

Before fitting, the five-column reduced direction design and every one-row deletion must be
full rank. After fitting, the full nonlinear Jacobian and every LOOCV Jacobian must be full
rank, all solvers must converge, bounded modeled margins must remain inside `(0, 1)`, and
LOOCV MAE must beat the same revenue-scaled mean-gross-margin benchmark used previously.
Condition numbers, parameter jackknife stability, V3 performance comparison, and the 2026Q1
stress result are report-only and have no post-hoc threshold.

Passing V4 does not authorize 2026Q3 evaluation, forecasting, valuation, target prices, or a
decision score. A future holdout protocol must be frozen separately before any 2026Q3 score is
opened.
