# SK hynix V5 2026Q3 prospective holdout and structural closeout

## Current scientific status

The product-margin structural development branch is closed for the current evidence set.
This is not a claim that DRAM, NAND, or Other profitability is unknowable in principle. It is
a narrower conclusion: aggregate company gross profit plus the currently certified product
revenue and direction-regime inputs did not support a stable latent product-margin
parameterization under the tested V1-V4 families.

Observed sequence:

- V1 produced useful empirical prediction but economically implausible literal component margins.
- V2 enforced bounded margins but lost nonlinear identification.
- the 2017-2018 third-wave expansion restored full algebraic source-design rank.
- V3 still lost fitted nonlinear rank after the logit link saturated component contributions.
- the V3 nullspace diagnostic isolated effectively absent Other sensitivity and a NAND weak-identification direction.
- V4 removed those unsupported degrees of freedom, yet the fitted nonlinear model again collapsed, with NAND contribution saturating at the lower boundary.

V5 therefore changes scope rather than continuing post-outcome surgery on the same structural
family. It directly models company gross profit with empirical regime and revenue-mix terms.
Its coefficients are **not** literal product margins, ASP elasticities, bit-volume elasticities,
or source-backed product gross-profit allocations.

## V5 development result observed before this protocol implementation

The frozen V5 method was registered before its fit metrics were seen. Its 21-row clean-panel
development run subsequently passed the preregistered development gate:

- full design rank: 7/7;
- all 21 leave-one-out designs: 7/7;
- LOOCV MAE lower than the unchanged leave-one-out mean-company-gross-margin benchmark;
- 2026Q1 remained contaminated report-only stress data;
- 2026Q3 remained unloaded and unevaluated.

These observations justify preparing the already-reserved prospective holdout. They do not
create authority to tune V5, refit V5, alter the holdout benchmark, or claim investment use.

## Frozen 2026Q3 protocol

`config/skhynix_company_gp_empirical_v5_q3_holdout_protocol.v1.yaml` is frozen before any
2026Q3 outcome exposure. It binds:

- method: `skhynix_company_gross_profit_empirical_regime_ols`;
- method version: `5.0-frozen-pre-fit`;
- method evidence id: the exact V5 manifest hash observed in the passed development run;
- fit evaluation date: `2026-08-18`;
- holdout: `2026Q3`;
- benchmark: training-mean company gross margin scaled by holdout company revenue;
- pass condition: model absolute error must be strictly lower than benchmark absolute error;
- refit before or after holdout: forbidden;
- first score: immutable and reused on repeated calls.

No condition-number, coefficient-stability, or error threshold was invented after seeing the
V5 development result.

## Two-stage holdout boundary

### 1. Readiness binding — allowed now

`alpha_cycle.sk_hynix_company_gp_empirical_v5_q3_holdout_readiness_cli`:

- reloads only the already-certified 21-row training panel and contaminated 2026Q1 stress row;
- reproduces the persisted V5 fit exactly;
- binds the exact fit evidence id, coefficients, training snapshot hash, and training-mean gross margin;
- writes a private validation binding;
- does **not** load 2026Q3 sources, target, or outcome.

### 2. One-shot scoring — forbidden until a certified Q3 bundle exists

`alpha_cycle.sk_hynix_company_gp_empirical_v5_q3_holdout_score_cli` has no network acquisition
path. It requires an explicit certified source bundle containing the 2026Q3 company revenue,
company gross profit target, NAND and Other revenue mix inputs, direction-regime codes, and
source evidence ids. The bundle must be complete, hash-bound, certified, and company/product
revenue reconciled before scoring.

The first accepted bundle spends the holdout. Later calls must reuse the same immutable result.
A changed bundle, changed V5 binding, or changed protocol is rejected.

## Important limitation: this is not yet an ex-ante investment forecast

V5 uses contemporaneous same-quarter revenue mix and cycle-driver direction inputs. Some or all
of those inputs may only become source-certified around the quarterly results release. Passing
2026Q3 would therefore validate an out-of-sample contemporaneous company-GP relationship, not
prove that the model can forecast gross profit before the market learns the quarter's inputs.

A separate ex-ante forecasting layer is required before this research can support a pre-earnings
numeric forecast or investment decision. That later layer must define what information is
actually available at the decision timestamp and must be validated under its own point-in-time
protocol.

## Disabled outputs

Regardless of V5 development status, and regardless of a future Q3 holdout result, the current
protocol does not enable:

- literal product-margin outputs;
- numeric forward forecasts;
- fair-value estimates;
- target prices;
- decision scores;
- automatic investment actions.
