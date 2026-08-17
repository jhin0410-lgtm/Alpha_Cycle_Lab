# SK hynix product-profitability regime v1 post-validation audit

## Why this audit exists

The frozen v1 regime estimator has two different claims that must not be conflated:

1. **Predictive claim** — the frozen 15-row model passed its pre-registered training gate and
   its one-time 2026Q1 holdout comparison.
2. **Structural/product-margin claim** — the fitted coefficients can be interpreted literally
   as DRAM, NAND, and other-product gross-margin contribution ratios.

A successful holdout establishes only the first claim. It does not automatically identify
product-level margins.

## Post-holdout status

This audit is intentionally **post-holdout**. It is not presented as another pre-registered
predictive validation test and it does not change the already-spent holdout result. V1 remains
immutable and cannot be refit after 2026Q1 exposure.

Influence diagnostics that were pre-registered as report-only remain report-only:

- maximum leverage
- maximum Cook's distance
- leave-one-out coefficient stability

No new pass/fail cutoff is assigned to those diagnostics after seeing the results.

## Structural accounting check

V1's equation multiplies product revenue by coefficients named as margin/intercept and
regime effects. If those coefficients are interpreted literally as standalone gross-margin
contribution ratios, then for a product with nonnegative cost of goods sold:

`gross margin = (revenue - COGS) / revenue <= 1`

The audit therefore evaluates every DRAM and NAND direction-regime combination over
`{-1, 0, +1} x {-1, 0, +1}` and records the implied margin envelope.

- Any implied ratio above `1.0` blocks literal structural/product-margin interpretation.
- A negative implied ratio is **not** an automatic failure because negative gross margin can
  occur during severe inventory or cost stress.
- The absolute size of the `other_margin_constant` is reported, but no post-hoc magnitude
  threshold is invented. The same `<= 1.0` nonnegative-COGS upper identity applies if it is
  interpreted literally as a standalone gross-margin ratio.

## Decision boundary

Possible outcomes are deliberately separated:

- `predictively_validated_structural_review_passed`
- `predictively_validated_structurally_noninterpretable`
- `predictive_validation_not_passed`

A predictive pass may therefore coexist with structural rejection. In that case v1 is kept as
validation evidence for a coarse regime predictor, but it cannot be promoted into a literal
DRAM/NAND margin decomposition, numeric forward-profit forecast contract, fair value, target
price, or investment decision score.

## V2 boundary

If v1 is structurally rejected:

- do not refit v1 to 2026Q1;
- do not call 2026Q1 unseen again in v2;
- use v1's failure mode only as research evidence for a separately versioned v2 design;
- prefer stronger identification, additional source variables, or an explicitly constrained
  structural formulation before opening another unseen holdout.

Run the local post-validation audit after the immutable training and holdout artifacts exist:

```powershell
$python -m alpha_cycle.sk_hynix_product_profitability_regime_post_validation_audit_cli
```
