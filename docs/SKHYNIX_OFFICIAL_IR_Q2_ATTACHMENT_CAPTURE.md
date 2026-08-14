# SK hynix official 2Q26 attachment capture

This stage consumes the reverified SK hynix Earnings Release board API artifact and captures
the PDF returned by the issuer itself.

It does **not** search for a PDF URL, enumerate attachment IDs, or use a third-party mirror.

## Source chain

The accepted chain is:

1. archived official SK hynix IR page and issuer JavaScript,
2. shared `GET /board/list` board route,
3. `UI-FR-IR06` bcode `105` / pageSize `200` / language contract,
4. raw issuer board JSON,
5. exactly one 2026 Q2 board row,
6. returned `cdnUrl`,
7. returned Q2 `fileUrl2`, and
8. issuer PDF bytes downloaded from the literal JavaScript composition contract
   `cdnUrl + fileUrl2`.

Any missing or ambiguous link stops the chain.

## URL safety

`fileUrl2` must be a relative path. The capture rejects:

- absolute URLs,
- scheme-relative URLs,
- query strings or fragments,
- backslashes/control characters,
- literal or percent-encoded `.` / `..` path traversal, and
- any composed URL that changes the hostname returned in `cdnUrl`.

The implementation deliberately uses string concatenation semantics matching the issuer
bundle. This preserves a returned CDN prefix such as `/web`; generic URL joining must not
drop that prefix.

## PDF fingerprint

The downloaded bytes must begin with a PDF signature and be readable by `pypdf`. The
capture records:

- SHA-256 and byte length,
- page count and extracted-text size,
- presence of `SK hynix`,
- a 2Q26 / Q2 2026 period anchor,
- `Revenue by Product`,
- `DRAM`,
- `NAND`, and
- bounded page-level text around `Revenue by Product`.

The context is intentionally retained without parsing percentages or revenue amounts. A
later source-specific parser must decide the exact semantics of any figures in the official
PDF.

`document_identity_verified=true` currently means only that the official PDF contains both
SK hynix identity and a 2Q26 period anchor. It does not mean product-mix semantics are
certified.

## Trust boundary

Even after a successful download all of these remain false:

- `product_baseline_eligible`
- `allocation_resolver_registered`
- `numeric_forecast_enabled`
- `decision_score_enabled`

The official PDF must next receive a checked-in parser/document contract. In particular,
DRAM/NAND shares must not be assumed to reconcile to company revenue and `Other=0` must
never be fabricated merely because displayed shares sum to 100%.

## Windows end-to-end capture

After the earlier official page/component artifacts exist, run:

```powershell
.\scripts\capture_skhynix_official_ir_q2_source.ps1
```

The script first resolves/captures the board API. The PDF stage is not attempted if the API
base is unresolved or the board response fails verification.
