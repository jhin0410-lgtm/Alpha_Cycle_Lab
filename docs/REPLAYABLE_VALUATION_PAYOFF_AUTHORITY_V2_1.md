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
| Canonically replayed OpenDART company actuals | Exact writer identity, OpenDART source, filing availability, CFS proof, semantic aliases, and KRW compatibility | A: authoritative persisted actual |
| `ValuationEvidenceSnapshot` share rows and market-cap arithmetic | Self-consistent normalized OpenDART payload and CSVs | B only after exact canonical replay; the current real snapshot fails that stricter replay and is treated as E |
| Market cap, trailing P/E, and P/B | Derived from the class-B share basis | blocked; never promoted to C |
| Cash actual | Official actual only when canonical bytes prove CFS | A when proven; otherwise blocked |
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
`c646cba2d4d855b77fde538e8637d60b45c861752c80e960554a8f38c850ecea` fully offline. The
legacy valuation snapshot `4eea4d515e77725c201ca773c95c651c87d0d48f28cca11b397c93c917161bdb`
did not reproduce its declared identity under the strict replay and was therefore excluded rather
than promoted to class B.

| Acceptance | 000660 SK hynix | 005930 Samsung Electronics |
| --- | ---: | ---: |
| Authority artifact | `36778c956b9d5f99f6931df51f29b5421b3173e3c0952202811ed5954bca39ee` | `922c14b0bde179cc1e090835dae20b1d89fc76b883bade662d8ee3784a1922c8` |
| Trusted current price | KRW 1,647,000/share | KRW 273,500/share |
| FY2025 net income | unavailable: persisted snapshot does not prove CFS basis | unavailable: persisted snapshot does not prove CFS basis |
| FY2025 book equity | unavailable: persisted snapshot does not prove CFS basis | unavailable: persisted snapshot does not prove CFS basis |
| FY2025 cash | unavailable: persisted snapshot does not prove CFS basis | unavailable: persisted snapshot does not prove CFS basis |
| Share-count authority | not established | not established |
| Complete capital-structure authority | not established | not established |
| Supported trailing methods | none | none |
| Supported forward methods | none | none |
| Price-implied requirement | blocked | blocked |
| Bear/Base/Bull values and payoff | typed blockers; values unavailable | typed blockers; values unavailable |

The August 14 canonical research bytes predate persistence of the OpenDART `fs_div` request, so
they cannot honestly distinguish CFS from OFS. The exact blockers for both are
`trailing_net_income_statement_basis_missing`, `book_equity_statement_basis_missing`,
`cash_and_cash_equivalents_statement_basis_missing`, `valuation_share_count_authority_missing`,
`valuation_capital_structure_authority_missing`, `trailing_ebitda_authority_missing`,
`forward_estimate_authority_missing`, `valuation_method_ineligible`, and
`scenario_input_authority_missing`.

## Integrity and publication

The authority artifact binds every source identity and the exact byte digest of every legacy
valuation file. Persistence uses an immutable timestamp/content directory, exclusive file creation,
file and directory fsync, atomic directory rename, no mutable latest pointer, exact schemas, file
digests, and mandatory upstream reconstruction. Persisted replay requires the canonical market,
research, and optional legacy directories, so a self-consistent payload cannot authorize itself.
Symlinks/junction aliases, unknown fields, duplicate identities, mutated
raw inputs, wrong generations/dates/securities, partial publications, and self-consistent forged
authority JSON fail closed.

The frozen SK hynix 2026Q3 prospective artifacts are neither read nor changed by this path.
