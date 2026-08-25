# Replayable valuation, price-implied expectations, and scenario/payoff authority v2.1

Issue #308 adds an authority boundary above the older normalized valuation, price-implied, and
payoff objects. Content-addressed arithmetic is not source authority: the new artifact starts
from canonical replay of the existing market and research writers and records every unsupported
input as a current blocker.

## Architecture and source audit

The repository audit found these distinct paths:

| Input/path | Previous behavior | Authority class after #308 |
| --- | --- | --- |
| Canonically replayed market `prices.csv` plus raw capture | Exact writer identity, PIT checks, KRW price | A: authoritative persisted source |
| Canonically replayed OpenDART company actuals | Exact writer identity and filing availability | A: authoritative persisted actual |
| `ValuationEvidenceSnapshot` share rows and market-cap arithmetic | Self-consistent normalized OpenDART payload and CSVs | B: replayable but semantically insufficient for share authority |
| Market cap, trailing P/E, and P/B | Derived from the class-B share basis | blocked; never promoted to C |
| Cash actual | Official CFS actual | A |
| Complete debt and EV bridge | No certified complete debt taxonomy/basis | E: unsupported |
| KIS forward cells and existing forward valuation | Opaque replayable cells with no numeric semantics | B/E; forward authority blocked |
| Reference multiple | Historical/peer evidence or explicit scenario input | D when assumed; never source authority |
| Existing price-implied snapshot | Inverts caller-supplied valuation evidence | blocked from authority |
| Existing payoff return ranges | Typed and probability-free, but numeric lineage may be caller supplied | blocked from valuation/payoff authority |
| DCF forecasts and capital cost | No complete versioned assumption pack | E: method ineligible |

The resilient and partial valuation wrappers improve missing-data behavior but do not establish a
new acquisition authority. The older package source revalidator correctly failed valuation and
price-implied canonical authority closed; #308 preserves that gate.

## Method eligibility

- Trailing P/E requires trusted price, trailing earnings, and an authoritative compatible share
  basis. Price and earnings are available, but share authority is not.
- Forward P/E requires authoritative forward EPS. KIS remains non-authoritative, so it is blocked
  independently from trailing P/E.
- P/B requires trusted price/share market capitalization and book equity. Book equity is official,
  but share authority is not.
- EV/EBITDA additionally requires a complete compatible debt/cash bridge and trusted EBITDA. Those
  requirements are not established.
- DCF remains ineligible because a complete versioned forecast/WACC assumption pack is absent.

Blocked methods expose no numerator, denominator, multiple, price-implied requirement, or scenario
value. Missing values are never replaced with zero.

## Scenario and package semantics

The artifact always records exactly one typed Bear, Base, and Bull case with a common horizon.
Each case binds the canonical market/research generations and persists its blockers. Because no
valuation method is eligible, implied per-share values and upside/downside are unavailable.
Probabilities, probability-weighted expected return, market consensus, target price, decision
score, sizing, recommendation, and execution all remain disabled.

This means Fast and Deep lanes cannot use a caller-created valuation, price-implied snapshot, gap,
or payoff range to bypass source authority. Existing Underwriter and Decision View fail-closed
checks remain unchanged.

## Real writer-backed acceptance (2026-08-14 sources)

Both acceptances replayed market snapshot
`8044d3b023eb8d70b6f0efed64861483fb5c4ce70141ba8df49cba51f8e79990`, research snapshot
`c646cba2d4d855b77fde538e8637d60b45c861752c80e960554a8f38c850ecea`, and legacy valuation
snapshot `4eea4d515e77725c201ca773c95c651c87d0d48f28cca11b397c93c917161bdb` fully offline.

| Acceptance | 000660 SK hynix | 005930 Samsung Electronics |
| --- | ---: | ---: |
| Authority artifact | `78ed8ac2e953911f7b2ae07f287aa14aa2d92e5c028f2e52741cd45fb583d9df` | `28ccade94d6590430e7cf9293591ee1ae9a74019611fba7c0ff437abe48d2837` |
| Trusted current price | KRW 1,647,000/share | KRW 273,500/share |
| Trusted FY2025 net income | KRW 42,947,902m | KRW 45,206,805m |
| Trusted FY2025 book equity | KRW 120,666,751m | KRW 436,320,337m |
| Trusted FY2025 cash | KRW 14,923,766m | KRW 57,856,378m |
| Share-count authority | not established | not established |
| Complete capital-structure authority | not established | not established |
| Supported trailing methods | none | none |
| Supported forward methods | none | none |
| Price-implied requirement | blocked | blocked |
| Bear/Base/Bull values and payoff | typed blockers; values unavailable | typed blockers; values unavailable |

The exact blockers for both are `valuation_share_count_authority_missing`,
`valuation_capital_structure_authority_missing`, `trailing_ebitda_authority_missing`,
`forward_estimate_authority_missing`, `valuation_method_ineligible`, and
`scenario_input_authority_missing`.

## Integrity and publication

The authority artifact binds every source identity and the exact byte digest of every legacy
valuation file. Persistence uses an immutable timestamp/content directory, exclusive file creation,
fsync, atomic directory rename, no mutable latest pointer, exact schemas, file digests, and
upstream reconstruction. Symlinks/junction aliases, unknown fields, duplicate identities, mutated
raw inputs, wrong generations/dates/securities, partial publications, and self-consistent forged
authority JSON fail closed.

The frozen SK hynix 2026Q3 prospective artifacts are neither read nor changed by this path.
