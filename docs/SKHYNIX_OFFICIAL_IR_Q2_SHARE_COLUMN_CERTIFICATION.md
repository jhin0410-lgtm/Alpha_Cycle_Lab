# SK hynix 2Q26 product-share period-column certification

This stage follows the verified official PDF source certification and product-page geometry
evidence. It certifies a narrower fact than a product-mix parser: which percentage tokens
belong to each quarter column.

## Source-shape contract

The pinned official 2Q26 deck must reverify through the existing geometry artifact and expose
one product chart with:

- the quarter sequence `'25 Q2`, `'26 Q1`, `'26 Q2` in that exact order;
- DRAM, NAND, and Others legend labels;
- exactly six product-side percentage tokens forming three two-token x-coordinate clusters;
- approximately regular left-to-right spacing between the three clusters;
- the exact source token pairs `77%/21%`, `78%/21%`, and `73%/27%` for those columns; and
- the issuer footnote stating that Revenue by Product portions are based on KRW with
  Solidigm results consolidated.

The rightmost cluster is therefore certified as the `'26 Q2` column with raw tokens
`73%` and `27%`.

## Important non-conclusion

This artifact deliberately does **not** identify which of the two current-quarter tokens is
DRAM versus NAND. Text geometry establishes a period column but does not by itself preserve
the chart-series color identity required for that pairing.

The chart also contains an `Others` legend. The visible DRAM/NAND-like token sums across the
three columns are 98%, 99%, and 100%. A current-column sum of 100% therefore does not certify
that current-quarter Other revenue is exactly zero. Integer display rounding or an unlabeled
small wedge must not be converted into a source fact.

Accordingly all of the following remain false:

- `product_assignment_certified`
- `other_zero_certified`
- `numeric_semantics_certified`
- `registry_write_eligible`
- `product_baseline_eligible`
- `allocation_resolver_registered`
- `numeric_forecast_enabled`
- `decision_score_enabled`

`ALLOCATION_SOURCE_RESOLVERS` must remain unchanged by this stage.

## Windows

After the geometry artifact has been captured, run:

```powershell
.\scripts\report_skhynix_official_ir_q2_share_column_certification.ps1
```

The command is offline with respect to SK hynix. It replays the existing verified geometry
chain and writes a reproducible share-column artifact.
