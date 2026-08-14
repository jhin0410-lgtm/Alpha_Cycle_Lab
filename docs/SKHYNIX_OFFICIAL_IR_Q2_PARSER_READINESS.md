# SK hynix 2Q26 parser readiness

This stage exists between official PDF capture and source-specific numeric parsing.

It re-verifies the archived official PDF and inventories the exact text around
`Revenue by Product`. It is intentionally incapable of certifying DRAM/NAND numeric
semantics.

## Output

The report records:

- official PDF URL and attachment evidence ID,
- board publication date,
- actual PDF page count,
- pages containing `Revenue by Product`,
- bounded source text and relevant lines,
- raw percentage tokens in source order,
- raw comma-formatted numeric tokens in source order,
- DRAM/NAND anchor presence, and
- a proposed parser ID for the later checked-in source contract.

For example, a report may expose raw tokens such as `73%`, `27%`, or `79,319`. Their
presence does **not** establish which metric each token represents. Layout, labels, units,
and denominator semantics must be certified in the next parser implementation.

## Readiness states

- `identity_not_verified`: the captured PDF did not satisfy SK hynix + 2Q26 identity.
- `product_mix_context_missing`: identity is valid but no usable DRAM/NAND
  `Revenue by Product` context was extracted.
- `context_ready_for_parser_contract_review`: exact official context exists and can be
  used to implement a source-specific parser.

Even the last state leaves `numeric_semantics_certified=false` and
`registry_write_eligible=false`.

## Non-goals

This stage does not:

- pair a percentage with DRAM or NAND,
- infer that two percentages sum to company revenue,
- infer `Other=0`,
- write `config/semiconductor_ir_documents.yaml`,
- register an allocation resolver, or
- enable forecasts or decision scores.

The next parser must encode the official layout and denominator semantics explicitly and
must fail closed if that layout changes.

## End-to-end Windows command

`capture_skhynix_official_ir_q2_source.ps1` now performs three stages:

1. board API capture,
2. official PDF capture,
3. parser-readiness context extraction.

```powershell
.\scripts\capture_skhynix_official_ir_q2_source.ps1
```

If an earlier stage is unresolved or invalid, later stages are not attempted.
