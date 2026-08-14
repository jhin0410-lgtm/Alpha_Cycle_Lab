# SK hynix 2Q26 Official IR Attachment Discovery

The 2026-07-15 SK hynix SEC 6-K states that the 2Q26 conference-call materials would be
available on the company's Investor Relations website on 2026-07-29. The official Earnings
Release page currently exposes the issuer's Azure Edge CDN, but automated page rendering can
produce an unresolved `webundefined` attachment target. The production registry therefore
must not guess a numeric `/web/attach/<id>.pdf` path.

This research tool resolves that transport problem without weakening source provenance.

## Discovery contract

The discovery command:

1. downloads the official SK hynix Earnings Release page,
2. archives the exact HTML bytes,
3. follows only JavaScript URLs explicitly referenced by that page and hosted on an
   issuer-controlled domain,
4. archives those JavaScript bytes,
5. extracts only PDF URLs literally present in the captured page or JavaScript bytes,
6. rejects third-party PDF hosts,
7. downloads every remaining explicit official PDF candidate,
8. verifies each candidate against the pinned FY2026 Q2 deck fingerprint,
9. archives all source bytes and writes a reproducible evidence pointer.

The tool never synthesizes an attachment ID from neighboring quarters, search-engine results,
or secondary mirrors.

## Pinned 2Q26 deck fingerprint

A matching PDF must have 19 pages and contain the observed company-authored deck anchors,
including:

- `2026.07.29`
- `FY2026`
- `Revenue by Product`
- `Revenue by Application`
- `Q3 B/G : Approx. 10% increase QoQ`
- `Began HBM4 shipment in Q2`

The product-revenue page must also contain:

- total revenue `79,319` KRW billion,
- DRAM `73%`,
- NAND `27%`.

These product-share values are used only as a fingerprint until the same bytes are recovered
from an explicit issuer-controlled URL. A secondary mirror is not eligible for the production
registry.

## Resolution semantics

`resolved=true` requires exactly one explicit issuer-hosted PDF candidate to pass the complete
fingerprint. Zero matches remain unresolved. Multiple matches also remain unresolved because
transport identity is ambiguous.

Even a resolved discovery artifact remains:

- `discovery_only=true`
- `product_baseline_eligible=false`
- `allocation_resolver_registered=false`
- `numeric_forecast_enabled=false`
- `decision_score_enabled=false`

A separate PR must still register the exact URL, source publication date, page count, parser
identity, and source bytes in the standard official-IR collection path.

## Windows usage

From the repository root:

```powershell
.\scripts\discover_skhynix_official_ir_attachment.ps1
```

The script prefers `ALPHA_CYCLE_PYTHON`, then `.venv\Scripts\python.exe`, then the system
`python`, and performs an `alpha_cycle`/`pypdf` dependency preflight.

Artifacts are written under:

```text
data/private/research/skhynix-official-ir-attachment-discovery
```

The command prints:

- `script_count`
- `candidate_count`
- `matching_candidate_count`
- `resolved`
- `resolved_url`
- `resolved_pdf_sha256`
- candidate-level source and fingerprint diagnostics.

If no explicit official PDF is present in the page or its referenced JavaScript, the next
safe step is to inspect the archived source diagnostics or a separately observed issuer API.
It is not safe to infer the numeric CDN path.
