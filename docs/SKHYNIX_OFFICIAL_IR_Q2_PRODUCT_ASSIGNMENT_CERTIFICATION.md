# SK hynix 2Q26 product-assignment certification

This stage follows the verified official-PDF source chain, product-page geometry evidence, and
period-column certification. It resolves one narrower ambiguity: which current-quarter
percentage token belongs to DRAM and which belongs to NAND.

## What the official PDF proves

The archived SK hynix FY2026 Q2 presentation page 16 contains a `Revenue by Product` stacked
bar chart. The prior stage already certifies the rightmost column as `'26 Q2` and verifies
that it contains the raw percentage tokens `73%` and `27%`.

This stage additionally replays the PDF vector content and verifies:

- a unique legend swatch immediately preceding each `DRAM`, `NAND`, and `Others` label;
- three distinct legend fill styles;
- a current-quarter bar segment containing the `73%` text position whose fill equals the
  DRAM legend swatch;
- a current-quarter bar segment containing the `27%` text position whose fill equals the
  NAND legend swatch;
- an additional positive-area current-quarter segment whose fill equals the `Others` legend
  swatch; and
- the three current-quarter segments share the same x extent and form one contiguous stack.

Therefore the source supports the following partial numeric semantics:

- DRAM share display: `73%`
- NAND share display: `27%`

`product_assignment_certified=true` and
`dram_nand_share_semantics_certified=true` are specific to those two displayed values.

## Important non-conclusion: Other is not zero

The current bar contains a visible `Others`-coloured vector segment, but that segment has no
numeric percentage token. The presentation footnote also states that figures are rounded to
KRW billions and may not add completely.

The implementation therefore does **not** derive an Other percentage from bar height, does
not calculate `100 - 73 - 27`, and does not convert the lack of an integer label into
`Other=0`.

These remain false:

- `other_zero_certified`
- `numeric_semantics_certified` (the complete product-mix numeric contract is still incomplete)
- `registry_write_eligible`
- `product_baseline_eligible`
- `allocation_resolver_registered`
- `numeric_forecast_enabled`
- `decision_score_enabled`

`ALLOCATION_SOURCE_RESOLVERS` remains unchanged. A separate current-period, source-bounded
Other-products amount/share or another explicitly justified reconciliation method is still
required before company revenue can be completely allocated.

## Why vector parsing instead of a screenshot

A screenshot is useful for human review but is not the production trust boundary. The
certification is rebuilt from the exact archived issuer PDF bytes. It parses painted PDF
rectangles and fill styles, then binds those shapes to text coordinates already preserved by
the verified geometry artifact. Persisted output cannot self-certify because the verifier
replays the upstream artifacts and source bytes before accepting the evidence ID.

## Windows

After the share-column artifact has been captured, run:

```powershell
.\scripts\report_skhynix_official_ir_q2_product_assignment_certification.ps1
```

The command is offline with respect to SK hynix. It uses the already archived official PDF
and re-verifies the complete upstream evidence chain before writing a new private research
artifact.
