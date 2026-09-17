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
| R1-B | In-memory pack/planner/revision contracts | Declarative loading, immutable version replay, governed promotion, cold-start proposal round trip, source-bound evidence |
| R1-C | Transmission observations and horizon package | Existing authority/source adapters, dated catalysts, company mapping, valuation/expectations integration, reproducible evidence views |
| R1-D | Challenge/hypothesis/gap contracts | Persisted challenge state, new missing-driver gaps, reasoning-model exchange and mandatory mature-round challenge |
| R1-E | Existing decision/forecast/outcome foundations | Connect authenticated outcomes and supported error analysis to prospective pack revisions |
| R1-F | Not accepted | Real PIT acceptance for memory, policy/backlog, long-cycle CAPEX, and cold-start domains; final twelve-capability matrix |

External code review is waived by the user's later instruction. Local regression
checks, CI, source authority, protected artifacts, and acceptance requirements
remain applicable. No real user decision or trade is synthesized for testing.
