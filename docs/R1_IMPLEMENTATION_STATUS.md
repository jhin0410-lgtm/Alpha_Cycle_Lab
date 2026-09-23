# Product R1 implementation checkpoint

Audit baseline: `578236bf` (2026-09-18). Product conclusion remains
`PRODUCT_R1_INCOMPLETE`. The rows below are working findings, not acceptance.

## Closure audit: important corrections

PRs #339/#341/#343 do not establish provider authority. A hash identifies
content; it does not authenticate its origin. `LiveTypedSourceManifest`
explicitly promises provenance-only byte replay. A locally generated fixture
can pass that replay. The original R1 wrapper mistook that for real PIT,
accepted caller-authored authority artifacts, and permitted boolean inputs
to accept a domain with missing capabilities. The boolean completion defect
was corrected in #349. The claim-specific consumption correction is described
below. These were internal defects, not external provider blockers.

The current process has OpenDART, BOK ECOS, KOSIS, KIS and Toss credential
variables. Values were not inspected or printed. Their presence is not proof
of access, but absence of credentials cannot currently be asserted. This
checkout initially contained only `data/sample/prices.csv`; that says nothing
about archives in other checkouts. New live checks use a separate ignored
`data/private/r1-closure-20260918` directory.

## Twelve-capability working gap matrix

Paths in this table are module names under `src/alpha_cycle`; `intelligence/`
contains the R1 modules unless otherwise noted. Runtime tests are synthetic
unless a separate live execution receipt is recorded.

| Capability | Actual code | Existing real-source path | Synthetic-only R1 proof | Dependency / missing integration | Next action |
| --- | --- | --- | --- | --- | --- |
| Macro/market | `fundamental_macro`, `market` | OpenDART/ECOS/Toss collectors and snapshot writers | R1 universe fixtures | Source snapshots not mapped into R1 universe | Capture and replay current official observations; bind fields |
| Universe/change/flow | `observable_universe`, `investor_flow_evidence` | Existing market/flow artifacts | Two-snapshot change tests | Provider-to-dimension mapping | Preserve raw/adjusted basis and source availability |
| Discovery | `surface_research_candidates` | Candidate engine can consume measured universe | Threshold candidates | Actual source-driven candidate execution | Run from persisted real observations |
| Planning | `persisted_research_plan_v1` | Validated current universe store | Driver binding tests | Real source bindings | Feed actual candidate into persisted planner |
| Packs | `research_model_runtime_v1`, `knowledge_pack_repository_v1`, `cold_start_research_v1` | No operational R1 live pack shown | Four-domain drafts/replay | Governed promotion and material driver evidence | Version source-bound packs and challenge them |
| Transmission | `deep_research_integration_v1`, semiconductor transmission modules | Existing accounting/product sources | Supplied observation objects | Company exposure and actual source joins | Bind hypothesis, assumptions, horizons to observations |
| Expectations/valuation | root `provider_forward_authority_v2_1`, `valuation_authority_v2_1` | KIS capture and OpenDART/market reconstruction | R1 only free-text availability state | Numeric authority and adapter into package | Reuse method eligibility; keep KIS consensus blocked |
| Catalysts/technical/flow | `catalyst_horizon`, technical and flow modules | Official disclosures and market capture | R1 IDs/status strings | Dated evidence and horizon integration | Attach dated source-backed state |
| Counter-thesis | `counter_thesis_loop_v1` | No live challenge demonstrated | Empty and supplied hypotheses | Persistent challenge and real contradiction search | Require evidence-bearing challenge in mature run |
| Forecast | `forecast_ledger`, root `forecast_tournament_opportunity_v2_1` | Protected prospective experiment | R1 infers forecast from learning object | Registration-to-research linkage | Reuse immutable registration and later-outcome contract |
| Synthesis/decision | research package v2.1, `DecisionMemory`, `prospective_decision_ledger_v2_1` | Existing typed research runner | Manual R1 object assembly | One integrated interface and full optional human record | Produce structured packet and append-only decision record |
| Learning | `outcome_learning_v1` | Existing forecast scoring foundations | Caller asserts authenticated IDs | Outcome source verification, lineage and supported attribution | Reconstruct outcome; preserve unknown error components |

## Existing source audit (scope, not blanket certification)

| Source | Acquisition/replay code | Provenance and safe semantic scope | Remaining check |
| --- | --- | --- | --- |
| OpenDART statements | `providers/opendart`, `fundamental_macro`, source revalidation | Receipt/company/account/period/raw payload; consolidated reported actuals only | Bind raw account/value to R1; capture time cannot recreate old vintages |
| OpenDART provisional | provisional earnings collector/loader | Registered receipt and normalized text; provisional company totals; archive bytes explicitly not retained | Live 2026-09-18 attempt failed on ambiguous net-income period marker; inspect parser, do not guess |
| OpenDART product revenue | product certification verifier and parser contract | Archived ZIP, receipt, period, independent parsing and amount reconciliation | Existing narrow SK hynix source contract; do not widen to forecasts |
| SEC company actual | SEC acquisition/decision loader; dual-official crosscheck | Pinned accession, issuer, period and company totals | Crosscheck object alone is not upstream authentication |
| ECOS | `providers/ecos`, macro collector/revalidation | Official series/item/cycle/unit; conservative retrieval availability | `BOK_ECOS_API_KEY` needs mapping to expected ECOS credential name; current vintage only |
| KOSIS | discovery/parameter/semiconductor history CLIs | Pinned table/item/classification/unit and revision-sensitive captures | Verify release availability and current API access; no historical vintage claim |
| Toss/Kiwoom | market writer, consistency and adjustment modules | Quotes/candles with exact adjustment basis | Live access and cross-provider comparability; no earnings/consensus authority |
| Investor flow | flow evidence/market-session modules | Provider-specific flow unit/window/session | Actual capture and scope check; no universal positioning claim |
| KIS estimates | provider-forward authority replay | Captured opaque cells, explicit uncertified numeric/consensus semantics | Missing independent field/forecast/consensus authority; credential presence cannot resolve semantics |
| Catalysts/disclosures | disclosure and catalyst evidence modules | Receipt/known-at/event windows | Integrate dates and uncertainty into R1 horizons |

No item in this table has yet met the user's irreducible-external-blocker proof
standard. Source verification, acceptance corrections and workflow integration
remain internally actionable. Completion and C1 planning must wait for that work.

### Live execution receipt, 2026-09-18

`FundamentalMacroCollector` fetched 2026 half-year CFS statements and disclosures
for 000660/005930 plus 30 days of ECOS base-rate/USD-KRW data using the existing
official clients. `write_fundamental_macro_snapshot` persisted the response and
`revalidate_research_snapshot` reproduced the identity:

`f0ea8c0dbdb94a263e8cb8e45de985761c821b2ba47617ab70a77f02d69856a6`

Capture time: `2026-09-18T09:36:26.705010+00:00`. Rows: 462 financial, 52 macro.
Local artifact: `data/private/r1-closure-20260918/research-intelligence/20260918T093626705010Z__f0ea8c0dbdb9`.
This is a current capture with exact byte/reconstruction evidence, not a
reconstructed historical vintage or a claim of independent numeric authority.
The next integration must use a research cutoff at or after this capture.

PRs #317, #319, and #321 added initial B/C/D contracts. Their merged/closed
status does **not** establish milestone acceptance. R1 remains incomplete.

## Handoff corrections

- Retain candidate blockers in planner readiness, reject foreign-domain packs,
  require references alongside claimed maturity, and retain optional gap semantics.
- Bind the complete candidate handoff into the research plan identity. Downstream
  packages reference this identity rather than incorrectly labelling a pack ID
  as a plan ID.
- Reject future observation cutoffs and mismatched candidate/package cutoffs.
  Date-only legacy cutoffs mean UTC midnight.
- Project observations only into explicitly declared horizons. Undated catalyst
  IDs remain package context and do not establish dated horizon relevance.
- Reopened gaps lose their prior maturity clearance while retaining old evidence
  references for investigation. Direct challenge constructors enforce lineage.

These checks validate supplied metadata; they do not independently authenticate
source references or establish source availability from captured provider data.

## Remaining acceptance work

| Milestone | Implemented foundation | Still required |
| --- | --- | --- |
| R1-A | Universe/change/candidate store and planner handoff | Reuse in full-loop acceptance |
| R1-B | Pack/planner/revision contracts; immutable version replay, cold-start exchange, persisted-observation evidence adapter | Governed promotion, real cold-start research round, additional source bindings |
| R1-C | Transmission observations and horizon package | Existing authority/source adapters, dated catalysts, company mapping, valuation/expectations integration, reproducible evidence views |
| R1-D | Challenge/hypothesis/gap contracts | Persisted challenge state, new missing-driver gaps, reasoning-model exchange and mandatory mature-round challenge |
| R1-E | Existing decision/forecast/outcome foundations plus immutable outcome-learning bridge | Persisted decision ledger integration, authenticated source adapter and supported error analysis across real research rounds |
| R1-F | Common four-domain/twelve-capability acceptance matrix and explicit blocker reporting | Real PIT/source-authority acceptance for memory, policy/backlog, long-cycle CAPEX, and cold-start domains |

External code review is waived by the user's later instruction. Local regression
checks, CI, source authority, protected artifacts, and acceptance requirements
remain applicable. No real user decision or trade is synthesized for testing.

## Knowledge-pack repository

`knowledge_pack_repository_v1` imports/exports the complete JSON pack schema and
stores exact `(domain_id, version)` bindings in SQLite. Identical retries succeed;
conflicting content for an installed version fails. Revisions require an existing
same-domain parent and rationale, and historical versions remain selectable.
Loading verifies schema, content identity, and row identity. There is no implicit
latest-pack selection or lifecycle promotion. Lifecycle labels in stored drafts
do not certify operational acceptance or source authority.

Writer-backed tests cover four synthetic domain identities, fresh-process-style
reopen, retained ancestors, tampering, duplicate keys, unknown fields/endpoints,
and concurrent identical/conflicting writes. These prove generic interchange,
not the required four-domain real-data R1-F acceptance.

## Cold-start reasoning-model exchange

`ColdStartRequest(candidate, proposed_version, requested_at).message()` exports
the full candidate-bound request for a reasoning model or connector. A response
contains `request_id`, `proposed_at`, `model_label`, and a declarative
`knowledge_pack` without `content_id`; the runtime calculates the hash.

`ColdStartProposalRepository.record(request, response_json)` checks the exact
request/domain/version, timestamps, source acquisition plans, material drivers,
transmissions and counter-thesis. Only root DRAFT packs are accepted. Established
models must use revision ancestry. AI-supplied evidence clearance is rejected;
required material-driver gaps are opened even when the response omits them.

`replay(request, proposal_id)` reconstructs the proposal from the stored original
response and verifies both request and resulting draft. The caller then selects
the draft for `KnowledgePackRepository.publish` and `build_research_plan`.
Recording proposals and installing versions are distinct operations: a failed
version installation retains the original proposal for examination and never
overwrites the installed version.

The module does not select or call an external model, authenticate suggested
sources, or promote a pack. Tests use explicitly synthetic model responses and
prove request -> response -> storage -> replay -> draft -> blocked plan, not
operational cold-start research or R1-F real-data acceptance.

## Persisted observations to research plan

`build_persisted_research_plan` reads the current successful R1-A store generation
and checks the candidate snapshot, cutoff, member scope and dimension metadata.
Each `DriverObservationBinding` explicitly identifies the source member,
dimension, metric, unit, basis, window, semantics and maximum source age.
The adapter inherits observation maturity; it cannot increase upstream authority.

Resolutions expose exact observation identities and `usable`, `missing`, `stale`,
`semantic_mismatch` or `insufficient_maturity` states. Missing/stale/mismatched
material drivers retain critical gaps. Failed current publication cannot reuse
an older successful snapshot. Different binding policies have different content
identities even when they select the same references.

Pass the complete `PersistedResearchPlan` to `build_deep_research_package` to bind
both the research plan and evidence-resolution policy into downstream identity.
Its payload retains the full resolution details for persistence by the caller.
This adapter uses the existing observation/replay trust boundary; it does not
independently re-fetch provider sources or authenticate a manually asserted
upstream authority level. Acceptance fixtures remain synthetic.

## OpenDART observation-to-plan interface (partial R1 integration)

### Acceptance correction

The legacy `evaluate_domain` boolean inputs are assertions, not proof. They no
longer promote synthetic research to real acceptance. Its available inputs do not
include source-specific authentication, immutable forecast replay, or independently
verified outcome evidence, so this compatibility evaluator reports `incomplete`.
It does not describe internally missing integrations as external provider blockers.
Missing capability execution remains `missing`; a pack ID or outcome-link object
alone remains `contract_only`. An empty counter-thesis object does not prove a
contradiction search. Research and challenge snapshots must match the plan, not
only its candidate ID. Product readiness also requires complete capability states,
no blockers, and real acceptance evidence rather than a top-level accepted label.

This fixes the false-positive completion path; provider-specific acceptance and
the actual missing execution integrations remain required work.

`python -m alpha_cycle.r1_research_cli` now connects an existing research-intelligence
writer directory to the persistent observable universe, change detection, research
candidates and partial research packets. This is not the complete R1 walkthrough.

Example (replace the source and output paths with your local artifact directories):

```powershell
python -m alpha_cycle.r1_research_cli --research-source SOURCE --store STORE --universe-id reported-actuals --version 1 --field '000660|memory_semiconductor|reported_revenue|CIS:ifrs-full_Revenue#34|2026-06-30|H1'
```

Repeat `--field` for additional securities or dimensions. Each selection binds
security, domain, dimension, exact account, period end and fiscal period. The CLI
uses consolidated statements; the Python adapter also supports explicit OFS.
Raw OpenDART company/request/account/receipt/value/currency reconstruction must
match the normalized field. `thstrm_amount` remains explicitly distinct from
`thstrm_add_amount`; no annualization or cumulative-period inference is performed.
Availability is no earlier than acquisition, not backdated to filing publication.

The first successful run establishes a baseline. Later measured changes produce
research candidates and JSON packets on stdout. With `--pack PACK.json`, exact
dimension-to-driver matches are resolved through the persisted observation store;
other material driver gaps remain open. Without a pack, the planner exposes model
acquisition requirements. No empty contradiction search, forecast or human decision
is invented. A failed new attempt hides the previous successful state; recovery
establishes a new explicit baseline, without a comparison across the failed gap.

On 2026-09-18 the CLI replayed the real OpenDART/ECOS receipt recorded above and
stored two reported-revenue observations for 000660 and 005930. Baseline snapshot:
`32640de5b530b08539749ac9b4043f4135df0d35298998a641d0da0b488cdff0`.
It emitted no change/candidate because this was the first acquisition baseline.
Changed-value and planning tests use explicitly synthetic writer fixtures; they
are not real-data change-detection or independent-authority acceptance.

The observation adapter supplies replayable evidence only. Replay cannot
authenticate remote origin. Optional live verification now supplies a separate
claim-specific authority manifest; it never sets Product R1 accepted or blanket
provider authority.

### Fresh official reported-field reconciliation

Add `--verify-official` to the R1 research command to independently retrieve the
selected company/filing fields from OpenDART's pinned HTTPS origin. Redirects are
rejected. Issuer, account, report period, CFS/OFS, receipt, currency and exact raw
`thstrm_amount` must agree with the archived selection. The verification timestamp
is generated after acquisition and cannot be backdated to the original capture.
Different receipts or restated values fail closed rather than altering history.

The CLI stores a content-addressed raw reconciliation receipt under
`STORE/reconciliations` and reports its exact field coverage. A live result can
validate only those observed fields at or after its own verification time. Copied,
manually constructed, altered or offline-replayed results do not inherit live
verification. Offline replay reconstructs the agreement, not remote origin.
This is not authority for forecasts, consensus, valuation assumptions or the
whole source archive. Existing observation maturity is not silently promoted.

The consumer binds exact observation/reference IDs; source changes during the
network call or between verification and publication are rejected. Publication
also compares the expected current attempt while holding the existing writer
lock. A competing success or failure causes `superseded`, preserving the winner
instead of comparing against a stale baseline or overwriting newer failure state.

Real execution on 2026-09-22 re-fetched the two 2026 H1 reported-revenue fields:
000660 receipt `20260814003509`, 005930 receipt `20260814003699`. Verification at
`2026-09-22T04:49:47.536662+00:00` produced reconciliation ID
`1d64b058ad8ca39be71c770dd4d93fd44bdeba01b0d81a7dee9461ef94e7ae2e`
and universe snapshot
`b5b8b68cbc1fb38333f95466bf556ec0dc91dcfa9efbb0d1c9ed56ef5708d3aa`.
Both fields were unchanged against the actual September 18 baseline. No research
candidate, forecast, human decision or Product R1 acceptance was fabricated.

### Claim-specific authority consumption

`build_opendart_source_authority_manifest` consumes the live-issued reconciliation
and the exact current observations. It derives provider/account/security/basis/
field/period/provenance scope from the verified claims rather than caller-supplied
authority strings. It can cover selected decision-critical references in a broader
universe while explicitly retaining lower-maturity research context. Original
observation maturity remains unchanged.

Generic source-byte replay and caller-authored authority artifacts establish no
remote origin, even with an official-looking provider label. Process-local live
issuance is bound to object identity and content: copying, reconstruction, nested
replacement or alteration cannot carry it to a different object or claim. Offline
receipt replay remains reproducible agreement, not reauthentication of origin.

The acceptance consumer requires matching snapshot/cutoff/candidate lineage and
decision-critical references used by the plan. A valid narrow manifest removes
only the corresponding source assertion blockers. Missing forecasts, learning,
counter-thesis and other capability executions still prevent product acceptance.

Real execution on 2026-09-23 verified the same two reported fields at
`2026-09-23T10:16:01.957195+00:00`. Reconciliation:
`e661333131d28d14e4508faf6e208d13e0f7221aa20ccd8bb00eb29934c3e7f8`.
Universe: `7e18fef9a7ce9d6b783d7c999d589afa20f704c58c1844e57eb16fabf3daf6f6`.
The CLI emitted claim manifest
`8f24b3a712624ba4223232fbf2e027be11d1c647e0029d92211bf94ada89ea65`
with real PIT/source authority for only those fields. Blanket provider authority
and Product R1 acceptance remained false. An earlier mismatched universe argument
failed closed; this successful run explicitly recovered a new baseline rather
than comparing across the failed attempt. No candidate or human decision was
fabricated.

Remaining internal work includes durable research-session replay, prospective
registration linkage, source-authenticated outcomes and full R1-E/R1-F execution.

## Decision memory and outcome learning

`DecisionMemory` is an optional, immutable user-action record bound to candidate,
current snapshot, research package and pack identities. The action enum includes
`observe` for a recorded research choice without implying a trade. Rationale,
invalidation conditions, thesis state and horizon are required; cost basis and
portfolio advice are outside this bridge.

`AuthenticatedOutcomeLink` requires registration, outcome and evaluation snapshot
identities plus SHA-256 source evidence IDs and an explicit authenticated flag.
The bridge validates the linkage shape but does not authenticate those IDs; the
existing forecast/source authority system remains responsible for producing them.
`ErrorContribution` preserves demand, supply, pricing, transmission, earnings,
catalyst timing, expectation/valuation, missing-variable and model-insufficiency
domains without converting one outcome into causality.

`build_outcome_learning_record` retains all historical inputs and optionally emits
a `ModelRevisionProposal` with the outcome evidence as trigger. A proposal has a
new version, parent content identity, rationale and a small-sample risk. It never
mutates the old decision, forecast, outcome or pack. Synthetic tests prove this
linkage and fail-closed behavior; they do not establish authenticated live data.
