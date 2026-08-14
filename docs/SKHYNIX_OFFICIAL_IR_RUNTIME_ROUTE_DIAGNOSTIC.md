# SK hynix official IR runtime-route diagnostic

## Purpose

The official SK hynix Earnings Release page and the eight issuer-controlled JavaScript
resources captured on 2026-08-15 exposed no literal PDF URL.  That makes a static
attachment-URL resolver insufficient, but it does **not** justify guessing a numeric CDN
attachment ID or probing arbitrary endpoints.

This diagnostic is the next source-bounded step.  It reverifies the existing official-IR
attachment-discovery artifact and then scans only those archived source bytes for literal
runtime data-access signals.

## What it scans

The source set is fixed by the previously captured discovery manifest:

- `official_ir_page.html`
- each archived `script_*.js` explicitly referenced by that official page

The source discovery artifact is reverified before any diagnostic output is accepted.
The diagnostic itself performs no network request.

It reports bounded contexts for:

- `fetch(...)`
- `axios(...)` / `axios.get(...)` style calls
- `XMLHttpRequest`
- jQuery `$.ajax`, `$.get`, `$.post`, `$.getJSON`
- quoted endpoint-like literals containing runtime-relevant tokens such as `api`, `ir`,
  `earnings`, `release`, `attach`, `download`, or `file`
- attachment/download/file contexts that may reveal how a runtime response is transformed
  into an issuer CDN URL

## What it does not do

The diagnostic does not:

- call a candidate API
- synthesize or guess an API path
- synthesize `/web/attach/<number>.pdf`
- treat an identifier such as `attachmentId` as a URL
- accept third-party data as production provenance
- register the SK hynix 2Q26 presentation
- enable product-baseline allocation, forecasts, valuation, scoring, orders, or trades

A literal route discovered here is only a candidate for a later, separately reviewed
source-specific network capture.

## Windows usage

First capture the source artifact with:

```powershell
.\scripts\discover_skhynix_official_ir_attachment.ps1
```

When that result is unresolved with `script_count > 0`, run:

```powershell
.\scripts\report_skhynix_official_ir_runtime_routes.ps1
```

The command defaults to the latest source pointer and the current Korea date.

Key output fields:

- `source_count`
- `network_call_site_count`
- `route_literal_count`
- `attachment_context_count`
- `source_summaries`
- `network_call_sites`
- `route_literals`
- `attachment_contexts`

## Interpretation

### Route literal + network call site

If the same archived script contains a plausible literal endpoint and a nearby network call,
that is the strongest next candidate.  The next implementation should pin the exact route,
request method, request parameters, and response schema before any live request is allowed.

### Network call site but no literal route

The route is probably assembled from constants or a client helper.  Use the emitted context
to trace the variable or helper definition in the archived script.  Do not infer the final
endpoint from naming alone.

### Attachment context but no network call

The script may only transform API response fields into a download URL.  Trace the response
field names first, then locate the separate data-fetching code path.

### No runtime signals

The data may be injected through a framework runtime, inline hydration, a worker, or another
resource class not included in the current source set.  Extend source discovery only after
that absence is demonstrated; do not fall back to attachment-ID enumeration.

## Trust boundary

Every runtime-route report is tied to the SHA-256 evidence ID of the reverified source
artifact.  The report has a separate deterministic evidence ID and is re-built from the
source artifact when loaded.  Persisted report counts or contexts cannot independently
activate anything.

The following remain fixed to false:

- `product_baseline_eligible`
- `allocation_resolver_registered`
- `numeric_forecast_enabled`
- `decision_score_enabled`
