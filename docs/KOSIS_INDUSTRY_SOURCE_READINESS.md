# KOSIS Industry Source Readiness

## Purpose

This layer captures official KOSIS mining/manufacturing evidence for future Korean semiconductor-cycle research. It does **not** certify the semiconductor cycle and does **not** change the investment decision score.

## What the live quantity-table probe established

The official table below is technically verified and ingestible:

- title: `품목별 광공업 생산·출하·재고·내수·수출량`
- organization ID: `101`
- table ID: `DT_1F02012`
- live verification date: `2026-08-09`

The live latest-period probe returned 330 rows, 66 classifications and five item IDs (`T40` through `T44`), but **zero semiconductor-related classifications**. Therefore this table is retained only as a supplemental product-volume source for classifications it actually contains. It is not the primary Korean semiconductor-cycle table.

The first inventory format also exposed an interpretation hazard: a single unit attached to an item could be mistaken for a universal unit even when units differ by product classification. Inventory schema v2 stores all unit variants observed for each item.

## Primary semiconductor source candidates

The corrected KOSIS research path uses two separate official-table candidates:

### 1. Industry production / shipment / inventory

Target title:

`시도/산업별 광공업생산지수(2020=100)`

Required before use:

- exact official table identity,
- verified `반도체 제조업` classification,
- exact production / shipment / inventory item IDs,
- stable unit/base interpretation,
- bounded monthly history.

### 2. Capacity / utilization

Target title:

`제조업 생산능력 및 가동률지수(2020=100)`

Required before use:

- exact official table identity,
- verified semiconductor classification,
- exact capacity / utilization item IDs,
- bounded monthly history.

These are separate evidence families. Capacity/utilization is not a substitute for shipment/inventory, and neither alone is sufficient to certify a memory-semiconductor investment cycle.

## Official API contracts

The implementation uses only the HTTPS KOSIS OpenAPI host:

- Integrated search: `https://kosis.kr/openapi/statisticsSearch.do?method=getList`
- Table metadata: `https://kosis.kr/openapi/statisticsData.do?method=getMeta&type=TBL`
- Parameter data: `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`

Strict JSON mode uses `jsonVD=Y`. The API key is loaded from local `KOSIS_API_KEY` and is never written into artifacts.

The parameter layer retains source identity, classification IDs/names, item IDs/names, unit variants, observation periods, values and `LST_CHN_DE` where provided.

## Run corrected semiconductor source discovery

```powershell
python -m alpha_cycle.kosis_semiconductor_source_discovery_cli
```

or after installing the console entrypoint:

```powershell
alpha-cycle-kosis-semiconductor-sources
```

This command does not rely on guessed table IDs. For each target title it:

1. searches the live official service,
2. requires exactly one exact title match,
3. independently verifies table metadata,
4. captures a latest monthly parameter inventory,
5. searches the returned classification hierarchy for semiconductor semantics,
6. preserves raw responses and an ASCII-safe latest pointer.

Outputs are written under:

`data/private/live-research/kosis-semiconductor-source-discovery/`

## Bounded history capture

Only after the discovery artifact exposes exact live IDs should a history request be made. The generic parameter CLI supports an independently verified table name and ID:

```powershell
python -m alpha_cycle.kosis_industry_parameter_cli `
  --table-id "<verified-table-id>" `
  --expected-table-name "<verified-table-title>" `
  --obj "<verified-objL1-code>" `
  --obj "<verified-objL2-code-if-required>" `
  --itm-id "<verified-item-id>" `
  --start 202001 `
  --end 202606
```

The exact number and order of `--obj` values must come from the live returned classification hierarchy rather than assumption.

## Revision and backtest boundary

KOSIS exposes `LST_CHN_DE` in parameter-data responses, but that is not a complete historical vintage archive. Current snapshots must not be represented as information necessarily available at each historical observation date.

Every artifact therefore remains:

- `revision_sensitive=true`
- `historical_vintage_certified=false`
- `industry_cycle_certified=false`
- `decision_score_enabled=false`

## Remaining engineering gates

1. live-verify the two corrected semiconductor source tables,
2. bind exact semiconductor classification and item IDs,
3. fetch bounded monthly histories,
4. validate units, missing observations, revisions and publication freshness,
5. derive descriptive production / shipment / inventory / utilization diagnostics,
6. add independent memory-price and supply evidence,
7. outcome-test proposed cycle regimes and decision policies,
8. only then consider integration with investment scoring.
