# Decision System v2.1 Underwriter

The Underwriter is a **research-readiness assembler**, not an automatic portfolio manager.
It answers whether enough point-in-time evidence exists for a human PM to review a thesis in
Fast Lane or Deep Lane. It does **not** turn a ready package into `investable_now`, BUY/SELL,
a target price, an optimal weight, or an order.

## Fast Lane

Fast Lane is available only for thesis statuses permitted by the frozen v2.1 guardrail:
`research_priority` and `underwriting`.

It requires the frozen minimum evidence set:

1. `why_now`
2. catalyst
3. transmission
4. expectation or priced-in assessment
5. top downside
6. counter-thesis
7. kill condition
8. position uncertainty

A full causal graph is **not** required in Fast Lane. Transmission may be represented by
content-addressed transmission evidence in `UnderwritingContextSnapshot`. This preserves the
intended speed advantage of Fast Lane while keeping provenance explicit.

A ready Fast Lane result is only:
`fast_lane_ready_for_human_review`.

## Deep Lane

Deep Lane requires every frozen v2.1 deep element:

- full causal graph
- forecast tournament
- certified expectation
- valuation
- payoff surface
- counter-thesis
- outside-graph scan
- opportunity-set comparison
- portfolio overlap

The Underwriter integration additionally requires three items that are economically necessary
for this implementation but do not rewrite the frozen guardrail list:

- conditional price-implied requirement
- catalyst
- kill condition

### Forecast tournament

Two forecast references are not sufficient. Registrations must be genuinely comparable:

- at least two registrations
- unique forecast ids and content-addressed snapshots
- same security
- same target variable
- same target date
- same unit
- same forecast origin
- same information cutoff
- same preregistered primary error metric
- at least two distinct `(forecaster_kind, model_family)` identities

Forecasts with shared dependency clusters may still be compared, but the Underwriter exposes
`forecast_dependency_overlap` rather than pretending they are independent.

### Certified market expectation

Deep Lane requires a certified market-consensus observation that is directly comparable to the
forecast tournament target: same security, target variable, target date, and unit. This prevents
an earnings forecast from being compared with an unrelated consensus metric.

### Valuation and price-implied views

Forward valuation must be bound to the exact expectation-state snapshot supplied to the
Underwriter. The price-implied requirement remains a separate conditional reverse-valuation
surface.

The architecture therefore preserves:

`our forecast != certified market expectation != conditional price-implied requirement`

## Epistemic defense

Counter-thesis and outside-graph discovery are consumed through the immutable
`EpistemicDefensePackageSnapshot`. High-materiality contradictions or blind spots do not get
silently averaged away. If all deep evidence is present but material epistemic flags remain,
the result becomes:

`deep_lane_ready_with_epistemic_flags`

not an investment approval.

## Opportunity set and portfolio overlap

The current repository does not yet have a richer generic typed opportunity-ranking or
portfolio-overlap object. `UnderwritingContextSnapshot` therefore binds SHA-256 provenance
references for those external comparison artifacts, while the thesis must also contain its
explicit `opportunity_set_refs` and `portfolio_overlap` assessment.

This is intentionally marked as reference-level binding rather than independent semantic
verification. A later cross-sectional opportunity engine can replace these generic references
without rewriting historical Underwriter snapshots.

## Immutable outputs

Both context and readiness snapshots are content-addressed. Persistence creates immutable
snapshot directories plus mutable `latest_*` pointers.

Every readiness payload explicitly keeps the following disabled:

- investability decision
- automatic thesis transition
- target price
- optimal position size
- automatic execution

## Research-boundary note

This integration is a separate Decision System v2.1 research layer. It does not alter the
frozen SK hynix 2026Q3 feature vector, model, forecast, benchmark, source capture, or outcome
scoring contract.

## Next gate

After this integration is validated, the highest-value next step is a real cross-sectional
**Opportunity Set / Capital Allocation engine**. It should compare actual candidates at the same
evaluation timestamp across expected return range, downside, earnings-revision potential,
catalyst timing, valuation/priced-in burden, flow/positioning, and overlapping risk drivers.
The output should rank research opportunities without claiming mathematically optimal weights
before calibration exists.
