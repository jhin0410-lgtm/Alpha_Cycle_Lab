# Product R1 implementation checkpoint

Verified baseline: `21967e408e0fcfc2b547bf6235e405dc8249bf5a`.

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
