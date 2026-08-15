# SK hynix official IR board API capture

This stage follows the verified SK hynix issuer board contract and Earnings Release
component contract.

The archived issuer JavaScript proves the board flow in two separate layers.

The shared board implementation proves:

- literal list route = `GET /board/list`,
- board response fields include `cdnUrl`, `list`, and `total`, and
- returned board rows carry attachment fields such as `fileUrl1..4`.

The `UI-FR-IR06` Earnings Release component separately proves:

- board category (`bcode`) = `105`,
- checked-in category mapping `실적발표=105`,
- page size = `200`,
- language selection = `KOR` / `ENG`, and
- Earnings Release PDF buttons are built from `board.cdnPath + fileUrl2`.

The live minified bundle does not attribute the shared `/board/list` helper call directly to
`UI-FR-IR06`. The production-facing orchestration therefore requires both source-backed
layers instead of inventing that component attribution.

Those facts do **not** by themselves prove the effective browser Axios base URL. The
capture therefore has a separate transport gate.

## Transport gate

`sk_hynix_official_ir_board_api_pipeline.py` re-verifies the archived official page,
issuer-controlled JavaScript, and component-contract artifact. It accepts an API base only
when an explicit literal assignment is present for one of:

- `browserBaseURL`
- `browserBaseUrl`
- `baseURL`
- `baseUrl`

Nuxt can serialize an otherwise literal URL with JSON unicode escapes, for example
`https:\u002F\u002Fhost.example`. Before the explicit-assignment scanner runs, the live
pipeline decodes only URL-structural slash/colon escapes (`\u002F`, `\u003A`) plus escaped
slashes. The archived source bytes and source evidence hash remain unchanged; this is only a
transport-literal normalization step. It does not decode arbitrary JavaScript escapes or
synthesize a host.

A framework fallback such as `http://localhost:3000`, the issuer page origin, a sibling
route, a CDN hostname, or a guessed API hostname is not sufficient. Multiple conflicting
browser bases also fail closed.

If the transport cannot be resolved uniquely, the CLI writes
`latest_skhynix_ir_api_transport_contract.json`, prints the source-derived contexts, sends
**no request**, and exits non-zero.

## Board capture

When the transport is uniquely resolved, the capture sends only the verified read-only
request contract:

```text
GET <resolved API base>/board/list
bcode=105
lang=ENG
page=1
pageSize=200
```

The raw JSON bytes are archived before any attachment is promoted. The response must be a
JSON object with:

- HTTPS `cdnUrl`,
- integer `total`, and
- `list` rows containing at least `seq`, `title`, and `displayDate`.

The capture records returned `fileUrl1..4` values verbatim. A lightweight 2026 Q2 title/date
classifier only marks rows for subsequent manual/source-specific review; it does not turn a
row into a registered source.

## Trust boundary

This stage is discovery-only. Even a successful board response leaves all of the following
false:

- `product_baseline_eligible`
- `allocation_resolver_registered`
- `numeric_forecast_enabled`
- `decision_score_enabled`

A returned `fileUrl2` must still be combined with the **returned** `cdnUrl`, downloaded as
issuer bytes, fingerprinted as the intended 2Q26 deck, and parsed under a checked-in
source-specific document contract before current-quarter product-mix evidence can be used.

## Windows

```powershell
.\scripts\capture_skhynix_official_ir_board_api.ps1
```

The launcher uses the repository `.venv` when available and derives the evaluation date in
Korea Standard Time.
