# SK hynix official IR board API capture

This stage follows the verified SK hynix Earnings Release component contract.

The archived issuer JavaScript already proves the following UI-FR-IR06 behavior:

- board category (`bcode`) = `105` for `실적발표` / Earnings Release,
- list route = `GET /board/list`,
- page = `1`,
- page size = `200`,
- language = `ENG` for the English page,
- the board response supplies `cdnUrl`, `list`, and `total`,
- Earnings Release PDF buttons are built from `board.cdnPath + fileUrl2`, and
- additional issuer attachments can appear in `fileUrl1`, `fileUrl3`, and `fileUrl4`.

Those facts do **not** by themselves prove the effective browser Axios base URL. The
capture therefore has a separate transport gate.

## Transport gate

`sk_hynix_official_ir_board_api_capture.py` re-verifies the archived official page and
issuer-controlled JavaScript bytes and accepts an API base only when an explicit literal
assignment is present for one of:

- `browserBaseURL`
- `browserBaseUrl`
- `baseURL`
- `baseUrl`

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
