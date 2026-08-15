# SK hynix 2Q26 official PDF source certification

## Why this stage exists

The first live official-PDF capture recovered the correct 19-page SK hynix FY2026 Q2 deck,
but parser-readiness v1 intentionally used a narrow period matcher and treated the issuer
board `displayDate` as a publication date.

The live source exposed two important format facts:

- the PDF uses forms such as `FY2026 Q2` and `’26 Q2`, and
- the board API can return a year placeholder such as `2026.01.01` for quarterly rows.

Neither fact justifies rewriting the old evidence. This stage is a new, separate artifact
that re-verifies the archived official PDF and certifies only what the PDF bytes themselves
support.

## Identity contract

The stage requires:

- the archived attachment pointer to reverify through the existing attachment loader,
- the PDF SHA-256 to match the attachment evidence,
- an `SK hynix` identity anchor,
- at least one supported 2026 Q2 period form in the PDF text, and
- a unique valid full calendar date in the PDF before `source_published_date` is certified.

Supported period forms include `2Q26`, `2Q'26`, `FY2026 Q2`, `2026 Q2`, `’26 Q2`, and the
Korean `2026년 2분기` form.

The board `displayDate` is retained as provenance only and is explicitly never promoted to
`source_published_date` by this stage.

## Product-page layout

For each page containing `Revenue by Product`, the stage records pypdf layout-mode text plus
raw percentage and comma-formatted number tokens. This is intended to preserve period/product
column relationships that normal text extraction can destroy.

The output still does **not**:

- pair a percentage with DRAM or NAND,
- decide whether 73%/27% use company revenue or another denominator,
- infer `Other=0`,
- reconcile product shares to company revenue,
- register a production document or allocation resolver, or
- enable a numeric forecast, valuation, score, order, or trade.

## Windows

After the official Q2 attachment has been captured, run:

```powershell
.\scripts\report_skhynix_official_ir_q2_source_certification.ps1
```

This command is offline. It reads the existing archived PDF and does not call the SK hynix
site or SEC.

The most useful output fields are:

- `q2_identity_anchors`
- `publication_date_candidates`
- `source_published_date`
- `document_identity_verified`
- `source_published_date_verified`
- `product_layout_pages`
- `readiness_status`

The desired state before writing a source-specific numeric parser is
`layout_ready_for_contract_review`.
