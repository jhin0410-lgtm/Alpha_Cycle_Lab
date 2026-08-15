# SK hynix 2Q26 product-page geometry evidence

This stage follows the verified official 2Q26 source-certification artifact. It exists
because flattened PDF text and layout-mode text still do not prove which chart label or
quarter column owns a percentage or revenue amount.

The stage re-verifies the source-certification chain, reuses the archived official PDF,
and reads only the certified `Revenue by Product` page(s). For each non-empty pypdf
`visitor_text` fragment it persists:

- fragment text,
- page number,
- text matrix,
- current transformation matrix,
- text-matrix x/y values,
- font size, and
- page width/height.

A focus view includes only product/application labels, DRAM/NAND/Others, quarter labels,
percentage tokens, and comma-formatted numeric tokens. The full fragment list remains in
the artifact for replay.

## Trust boundary

Coordinates are review evidence, not numeric semantics. This stage does **not**:

- assign 73% or 27% to DRAM/NAND,
- assign 52,576, 22,232, or 79,319 to a quarter,
- infer that `Other` is zero,
- certify a denominator,
- register a current allocation resolver, or
- enable forecasts, valuation, decision scores, orders, or trades.

All downstream trust flags remain false.

## Windows

After source certification has been captured:

```powershell
.\scripts\report_skhynix_official_ir_q2_product_geometry.ps1
```

The command is offline with respect to SK hynix: it reuses the archived PDF already bound
to the source-certification chain.
