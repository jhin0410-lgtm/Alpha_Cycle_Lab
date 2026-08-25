# Provider-specific forward estimate authority v2.1

## Authority audit

The milestone audited the KIS research adapter and raw expectation snapshots, KIS historical
semantic crosschecks and normalized/revision artifacts, `ExpectationStateSnapshot`, expectation-gap
construction, OpenDART provisional earnings, semiconductor forward inputs, Decision View inputs,
and the Research Package canonical/source-revalidation gates.

The source classes remain distinct:

| Source | Class | Authority actually available |
|---|---|---|
| OpenDART filings and provisional earnings | A — official issuer actual | Official company-level actuals for the covered reporting periods. Provisional earnings are actuals, not guidance. |
| Issuer IR/filing forward statements | B — official issuer guidance | No normalized numeric guidance contract with replayable range/period semantics is currently available. |
| KIS `estimate-perform` | F — unsupported/unknown provenance, financial, and aggregation semantics | The persisted capture's declared KIS provider, endpoint, TR, symbol, timestamps, raw archive bytes, original-response hash metadata, and opaque response cells are replayable. Original provider provenance and the financial meaning of the forward cells are not authoritative. |
| KIS normalized forward rows | F — unsupported/unknown | Historical actual comparisons support narrow row/scale hypotheses, but first-party KIS schema material does not certify forecast-column alignment or scale continuity. The existing numeric gate remains closed. |
| KIS snapshot comparisons | F — unsupported/unknown revision semantics | Only one distinct persisted source vintage exists. No historical revision authority is available. |
| Semiconductor forward-input evidence | E — derived/model input | Bounded qualitative/model evidence; not issuer guidance, provider estimate, or consensus. |
| Expectation State and expectation gap | Normalized/derived state | Never source authority. Each trusted side must independently replay from its own registered source contract. |

There is currently no class C single-broker estimate, class D multiple-provider consensus, or
class B official issuer guidance source whose exact semantics are independently replayable. The
`name1` value in KIS `output1` is not sufficient evidence to infer a single-broker producer or a
consensus population.

## KIS provider replay contract

`provider_forward_authority_v2_1` binds the exact persisted KIS source manifest, records archive,
and `raw_estimate_perform.json` bytes. It validates the fixed provider, endpoint, TR ID, source
scope, securities, capture/retrieval timestamps, original HTTP response hashes, and source
snapshot identity. The normalized authority artifact is content-addressed and embeds exact copies
of those source bytes. Replay performs no network calls and reruns only the registered KIS parser.

The persisted JSON payload is a decoded/serialized archive, not the original HTTP response body.
Accordingly, `original_http_response_bytes_archived=false`; the original HTTP SHA-256 values are
retained as capture metadata and are not misrepresented as locally recomputable hashes. Because
there is no trusted capture attestation or recomputable original response, content addressing proves
only integrity of the persisted capture and deterministic replay. It does not independently prove
that KIS emitted the bytes, so `provider_source_authority=false`.

The parser records `output2`/`output3` values only as opaque provider cells. `output4.dt` is retained
as a period-label candidate, while the unsupported positional relationship is explicit. It does
not emit typed metrics, normalized numeric values, units, currencies, guidance, single-broker
identity, consensus, or revisions. Unsupported values remain null rather than becoming zero.

Publication uses immutable timestamp/content-addressed directories and no mutable latest pointer.
Readers reject symlinks, Windows reparse points, path escapes, malformed UTF-8/JSON, incomplete
files, byte mutations, normalized mutations, parser drift, stale expected identities, duplicate
authority resolution, and sources captured after the evaluation date.

## Package boundary

`ExpectationStateSnapshot` still normalizes typed observations but cannot certify its source.
Research Package revalidation resolves `source_evidence_id` only through a registered
provider-specific repository and reruns provider parsing. Unknown providers and caller flags fail
closed. Current KIS artifacts return `provider_capture_replay_integrity=true` but
`provider_source_authority=false`, `provider_forward_numeric_authority=false`,
`market_consensus_authority=false`, and `revision_authority=false`; therefore they cannot authorize
an Expectation State, Fast/Deep expectation gap, valuation input, or opportunity publication.

The assembler retains all underwriting, payoff-surface, Decision View, and expectation-gap
blockers. A referenced expectation whose upstream provider replay cannot authorize it additionally
surfaces `provider_source_replay_mismatch`. No valuation, target price, payoff, position size,
recommendation, or execution capability is created.

## Real-source acceptance: 2026-08-10 capture

Source snapshot:
`b5c6cd763004946dff2d090482866094ade6a0119f82bfd58afc6c61f6c7592d`.

| Capability | 000660 SK hynix | 005930 Samsung Electronics |
|---|---|---|
| Official actual financials | Available through separate OpenDART actual paths; not promoted by KIS | Available through separate OpenDART actual paths; not promoted by KIS |
| Official issuer guidance | Unsupported | Unsupported |
| Provider forward EPS | Unsupported: no authoritative KIS metric binding | Unsupported: no authoritative KIS metric binding |
| Provider forward revenue | Opaque KIS cells captured; numeric financial authority blocked | Opaque KIS cells captured; numeric financial authority blocked |
| Provider forward operating profit | Opaque KIS cells captured; numeric financial authority blocked | Opaque KIS cells captured; numeric financial authority blocked |
| Estimate revisions | Baseline/current endpoint only; no historical revision authority | Baseline/current endpoint only; no historical revision authority |
| Genuine market consensus | Not established | Not established |

Use the CLI with an explicit source directory and cutoff:

```text
alpha-cycle-provider-forward-authority-v2-1 publish --source SOURCE_DIR \
  --evaluation-date 2026-08-10 --research-cutoff-at 2026-08-10T13:33:13.144358+09:00 \
  --output-root ARTIFACT_ROOT/provider_forward_authority_v2_1

alpha-cycle-provider-forward-authority-v2-1 replay --artifact ARTIFACT_DIR \
  --evaluation-date 2026-08-10 --research-cutoff-at 2026-08-10T13:33:13.144358+09:00 \
  --expected-artifact-id SHA256
```
