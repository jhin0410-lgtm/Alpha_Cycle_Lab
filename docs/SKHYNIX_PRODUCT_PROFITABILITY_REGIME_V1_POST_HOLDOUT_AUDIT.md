# SK hynix product-profitability regime v1 post-holdout audit

## Outcome boundary

The frozen v1 direction-regime model passed its pre-registered training gate and the immutable
2026Q1 holdout benchmark. That validates the existence of empirical predictive signal under
the frozen v1 specification. It does **not** make each fitted coefficient a directly observed
DRAM/NAND product gross margin.

## Accounting-hard-bound review

For literal product gross-margin interpretation, gross profit cannot exceed product revenue
when cost of sales is non-negative. The post-holdout audit therefore enumerates every
`ASP sign x bit-volume sign` regime for DRAM and NAND and checks the hard upper bound of 1.0.
This is an accounting identity check, not a post-hoc fitted performance threshold.

If any enumerated implied contribution ratio exceeds 1.0:

- v1 predictive validation remains intact;
- literal structural product-margin interpretation is blocked;
- v1 is scoped to `validated_empirical_regime_predictor_only`;
- no forward structural forecast, fair value, target price, or decision score is enabled;
- v1 is never refit to the already-spent 2026Q1 holdout.

## Next research round

A v2 method must be registered independently. It should incorporate economic constraints or a
better-identified product-profitability parameterization before fitting, and must reserve a
new future holdout rather than reusing 2026Q1 as an independent test. Historical/pseudo-holdout
experiments may be used for method development but must not be mislabeled as a new untouched
holdout.
