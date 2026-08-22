# Prospective Opportunity Scorekeeping v2.1

## Purpose

The Decision System now has a same-date/same-horizon Pareto opportunity set and a certified expectation-gap overlay. The next requirement is not another heuristic ranking dimension. It is prospective evidence showing whether the frozen decision surface actually identifies better opportunities.

This layer therefore separates two times explicitly:

1. **registration time** — the opportunity set, frontier, leader, benchmark, horizon, and price basis are frozen;
2. **outcome time** — only after the complete future trading-session horizon closes may realized outcomes be attached.

The scorer is an evaluation instrument. It does not recommend portfolio weights or execute trades.

## Ex-ante registration

`ProspectiveOpportunityRegistration` freezes:

- evaluation date;
- deterministic entry session;
- 60 / 120 / 250 trading-day horizon;
- base opportunity-set snapshot ID;
- optional expectation-gap overlay snapshot ID;
- the complete candidate security set;
- base Pareto frontier;
- optional expectation-augmented Pareto frontier;
- optional unique leaders from each surface;
- benchmark security;
- adjusted price basis;
- source evidence and Decision System guardrail evidence.

The contract explicitly records that candidate, benchmark, horizon, and price-basis selection did not occur after observing outcomes.

## Entry-session rule

The frozen entry rule is:

```text
next_available_session_close
```

If registration occurs before the current trading session closes, that close is the entry session. If registration occurs after the close or on a non-trading day, the next valid trading session becomes the entry session.

This avoids using a close that was already known when the decision observation was registered while still supporting weekend and post-close research workflows.

## Trading-session horizon

A 60-day observation means exactly **60 exchange trading sessions after the frozen entry close**, not 60 calendar days.

The scorer derives every required session through the repository trading-calendar protocol. A candidate or benchmark missing any required session fails closed. It is not silently forward-filled or scored on a shorter window.

## Price-basis boundary

Schema v1 rejects `raw` prices.

The permitted bases are:

- `split_adjusted`;
- `total_return_adjusted`.

The observed market-data basis must exactly match the registered basis, and `adjusted_close` must be complete and positive for every required session.

This prevents stock splits from being misclassified as investment losses or gains. `total_return_adjusted` should be preferred when the upstream source has a certified dividend-reinvestment interpretation. The scorer does not invent that certification itself.

## Realized metrics

For each registered candidate the scorer records:

- entry and exit adjusted close;
- realized basis return;
- benchmark excess return;
- maximum close-to-close favorable excursion;
- maximum close-to-close adverse excursion.

The excursion metrics deliberately use the adjusted-close path rather than raw intraday high/low data. This avoids false precision when only the close series has a certified corporate-action adjustment basis.

## Opportunity-set diagnostics

The outcome snapshot records:

- ex-post winner or tied winners;
- best realized return available inside the frozen base Pareto frontier;
- base-frontier regret versus the best registered candidate;
- whether the base frontier contained an ex-post winner;
- regret of the frozen unique base leader, when one existed;
- equivalent diagnostics for the expectation-augmented frontier;
- incremental best realized return from the expectation overlay versus the base frontier.

These fields answer different questions.

`base_frontier_regret` asks whether the original payoff/catalyst surface excluded a materially better registered alternative.

`expectation_overlay_incremental_best_return` asks whether adding a preregistered market-expectation dimension improved or degraded the best opportunity retained on the frontier.

Neither field is a causal proof from one observation. They become useful after many prospective observations accumulate.

## Fail-closed rules

The scorer refuses to evaluate when:

- the registered horizon has not closed;
- the observed price basis differs from registration;
- the frozen entry session does not match the deterministic entry rule;
- the entry session is not a valid trading session;
- any required candidate or benchmark session is missing;
- adjusted prices are missing, non-numeric, or non-positive;
- the registration uses raw prices.

No outcome is partially scored.

## Persistence

Registrations and outcomes are content-addressed snapshots. Persistence refuses to replace an existing file. Registration artifacts should therefore be committed or otherwise immutably retained before the future outcome window closes.

## Explicitly disabled

- post-outcome candidate substitution;
- post-outcome benchmark substitution;
- post-outcome horizon selection;
- weighted ranking retrofits;
- target prices;
- position sizing;
- capital-allocation recommendations;
- automatic execution.

## Interpretation discipline

A single 60-day win does not validate a decision rule. The purpose of this layer is to build a prospective sample that can later support calibration by horizon, regime, sector, thesis type, expectation-gap state, and model competence.

The eventual learning loop should distinguish at least:

- correct thesis and correct repricing;
- correct fundamentals but already priced in;
- correct thesis with delayed catalyst;
- macro/regime override;
- valuation compression;
- frontier-selection error;
- leader-selection error;
- timing error.

## Frozen SK hynix boundary

This layer is generic Decision System infrastructure. It does not modify or execute the frozen SK hynix 2026Q3 prospective gross-profit experiment or its preregistered outcome scorer.

## Next gate

After this scorer is stable, the next high-value step is a **prospective decision ledger and attribution layer** that aggregates many immutable registrations/outcomes and groups errors by decision component rather than optimizing a new weighted score from a tiny sample.
