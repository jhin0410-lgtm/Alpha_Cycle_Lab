# Certified Expectation State — Decision System v2

## Purpose

The investment question is not only whether a company's fundamentals are improving. It is whether the
system's fundamental view differs from the expectation already embedded in the market.

Decision System v2 therefore treats forward expectations as a first-class point-in-time state:

```text
OUR FUNDAMENTAL VIEW
        vs
CERTIFIED MARKET EXPECTATION
        vs
PRICE-IMPLIED EXPECTATION
```

This layer implements the middle object. It does not create an expectation from an uncertified feed and
it does not yet calculate the expectation gap or a target price.

## Why a new state object is needed

The repository already has two important pieces:

1. `expectation_gap_contract.py` decides whether a provider's forward level and revision semantics are
   usable.
2. the KIS `estimate-perform` pipeline preserves raw and historically crosschecked forward values while
   refusing to call them market consensus.

What was missing was a provider-agnostic numeric object that can represent a *successfully certified*
forward expectation once a suitable source exists.

`expectation_state.py` fills that gap.

## Observation contract

A `CertifiedExpectationObservation` records:

- provider;
- security;
- metric;
- fiscal target period and period end;
- expectation kind;
- numeric value and unit;
- observation timestamp;
- source evidence hash;
- provider/metric/period/aggregation/timestamp semantic certification;
- optional producer identity;
- optional aggregation method, estimate count, and dispersion.

Supported expectation kinds are deliberately distinct:

- `market_consensus`;
- `single_broker`;
- `management_guidance`;
- `provider_defined_estimate`.

A provider-defined estimate can be numerically usable without becoming market consensus.

## Consensus gate

The word `market_consensus` is a stronger economic claim than "forward number exposed by an API".

A record may use `market_consensus` only when:

1. the generic expectation level contract passes;
2. `market_consensus_certified=true` is supplied independently;
3. an aggregation method is identified.

This prevents a value from becoming consensus merely because multiple periods or generic DATA fields
exist in a response.

## KIS boundary

As of the current repository evidence and the official Korea Investment OpenAPI sample, KIS
`estimate-perform` still does not authoritatively document the producer/aggregation semantics needed to
identify its forward rows as market-wide consensus.

Therefore the existing KIS feed remains outside `ExpectationStateSnapshot` as a certified numeric market
expectation. Historical cross-source row identification and deterministic forward normalization do not
satisfy this stronger gate.

The KIS artifacts remain useful research evidence and can be promoted later only if authoritative
semantics are established.

## Point-in-time snapshot

`ExpectationStateSnapshot` is content-addressed and requires:

- timezone-aware capture time;
- explicit evaluation date;
- no observation timestamp after the capture;
- no observation available after the evaluation date;
- a still-forward target period;
- unique provider/security/metric/period/kind observations;
- content-addressed source snapshot references.

The snapshot is independent of the existing v1 composite score.

## Revision contract

A change between two forward estimates is not automatically a certified estimate revision.

`build_expectation_revisions()` requires:

- two separately frozen snapshots;
- the same provider/security/metric/target/kind key;
- the same unit and target-period end;
- no drift in source scope, producer identity, aggregation method, or consensus certification;
- certified provider vintages;
- certified comparable snapshot scope;
- certified revision calculation semantics.

Only then are absolute and relative changes materialized as `ExpectationRevisionObservation`.

If these requirements fail, the system either blocks the revision or fails closed on semantic drift.

## Persistence

`persist_expectation_state()` writes an immutable content-addressed snapshot directory plus a mutable
`latest_expectation_state.json` pointer.

The immutable directory contains:

- `manifest.json`;
- `expectations.json`.

The manifest records provider identities, observation count, consensus observation count, source snapshot
IDs, and the invariant `order_api_enabled=false`.

## What this layer does not do

It does not:

- certify KIS as consensus;
- invent a consensus from one or more broker values;
- scrape analyst estimates without source timestamps;
- backfill historical vintages from today's values;
- calculate fair value;
- change the current v1 decision score;
- compare an internal forecast with the external expectation yet;
- enable trading.

## Next integration gate

Forward valuation may consume an expectation observation only after this contract accepts it.

The next Decision System v2 layer should therefore bind:

```text
PIT market price / share count / enterprise value
                  +
CertifiedExpectationObservation
                  ↓
Certified forward valuation state
```

If no certified expectation exists, forward valuation must remain unavailable rather than silently
falling back to the existing trailing actual multiple.
