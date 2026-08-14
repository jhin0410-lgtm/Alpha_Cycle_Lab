# SK hynix official IR component-contract diagnostic

This diagnostic is the focused follow-up to `SKHYNIX_OFFICIAL_IR_RUNTIME_ROUTE_DIAGNOSTIC.md`.

The live 2026-08-15 runtime-route artifact showed that the official Earnings Release page is hydrated at runtime: the server-rendered link is `.../webundefined`, while archived issuer JavaScript constructs download links as `board.cdnPath + fileUrlN` and contains the literal detail route `/performance/detail`.

The broad runtime scanner is intentionally noisy because it reports generic `fetch`, axios, file, download, and route contexts across the Nuxt runtime. This component-contract diagnostic instead extracts only syntactically constrained facts from the same already archived and reverified issuer bytes.

## What it extracts

- literal `execute.get/post(context, "/route", ...)` call contracts;
- `board.parameter.bcode = <integer>` assignments;
- explicit earnings-category code mappings such as `"실적발표": <integer>`;
- literal `cdnPath: "https://..."` values;
- exact `cdnPath + ...fileUrl1..4` bindings;
- bounded method windows around `queryBoardList`, `setBoard`, and `queryBoardView`.

Each signal records the archived source file, source URL, nearest component name, exact extracted value, and bounded context.

## Trust boundary

This diagnostic:

- performs no network I/O;
- never synthesizes an API route;
- never guesses a CDN attachment ID;
- cannot register a product baseline or allocation resolver;
- cannot enable a numeric forecast, valuation, score, order, or trade.

A route is emitted only when it is literally the route argument of the constrained `execute.get/post` call shape. A string such as `attachmentId` or a standalone route-looking constant is not enough.

The persisted report does not self-certify. Loading the report first reverifies the original official-IR attachment-discovery artifact, rereads its archived page/JavaScript bytes, rebuilds every contract signal, and requires the deterministic evidence ID and report payload to match.

## Windows usage

After `discover_skhynix_official_ir_attachment.ps1` has produced the source artifact:

```powershell
.\scripts\report_skhynix_official_ir_component_contracts.ps1
```

The most decision-useful output fields are:

- `execute_routes`
- `bcode_assignments`
- `earnings_code_mappings`
- `cdn_paths`
- `file_url_bindings`
- `method_windows`

## Interpretation

The next network-capture step is allowed only after the archived issuer JavaScript gives an exact route plus the relevant request parameter contract.

For the Earnings Release page, the desired result is an exact list route tied to the earnings board configuration, not an inferred sibling of `/performance/detail`. Once that route and its `bcode`/parameters are source-bound, a separate capture module can request the official endpoint, archive the raw response bytes, verify the response schema, and identify the `fileUrlN` field that resolves against the issuer CDN prefix.

Even then, the resulting PDF must independently match the pinned FY2026 Q2 deck fingerprint before any current-quarter product-mix source is considered for registry activation.
