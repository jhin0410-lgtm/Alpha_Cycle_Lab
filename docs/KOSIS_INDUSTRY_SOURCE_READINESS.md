# KOSIS Industry Source Readiness

## Purpose

This layer discovers and captures official KOSIS evidence needed for a future Korean semiconductor production/shipment/inventory cycle signal. It does **not** certify the semiconductor industry cycle and does **not** change the investment decision score.

Verified target table:

- title: `품목별 광공업 생산·출하·재고·내수·수출량`
- organization ID: `101`
- table ID: `DT_1F02012`
- live identity verification date: `2026-08-09`

## Official API contracts

The implementation uses only the HTTPS KOSIS OpenAPI host:

- Integrated search: `https://kosis.kr/openapi/statisticsSearch.do?method=getList`
- Table metadata: `https://kosis.kr/openapi/statisticsData.do?method=getMeta&type=TBL`
- Parameter data: `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`

Strict JSON mode uses `jsonVD=Y`. The API key is loaded from local `KOSIS_API_KEY` and is never written into artifacts.

## Current certification boundary

The discovery command verifies:

1. official KOSIS host,
2. integrated-search result identity,
3. exactly one exact Korean table-title match,
4. table-title agreement with the independent table metadata endpoint,
5. immutable raw search and metadata response hashes.

The parameter-data layer additionally verifies:

1. expected organization and table IDs on every returned row,
2. expected publication period type,
3. non-empty classification and item identity,
4. unique observation keys,
5. exact table-title agreement,
6. immutable raw and normalized response hashes.

Every artifact explicitly records:

- `historical_vintage_certified=false`,
- `industry_cycle_certified=false`,
- `decision_score_enabled=false`.

## Why revision provenance is mandatory

KOSIS exposes `LST_CHN_DE` (last modification date) in parameter-data responses. This field is retained in the artifact inventory, but it is not a complete historical vintage database.

The target table is known to be revision-sensitive. Therefore a current KOSIS snapshot must not be represented as information that was necessarily available at the historical observation date. Backtests remain revision-sensitive unless archived vintages are independently obtained.

KOSIS alone supports a narrowly scoped Korean mining/manufacturing production-shipment-inventory view. It is not sufficient to certify the broader memory-semiconductor cycle, which also needs memory price and supply evidence.

## Run table discovery

Set a local KOSIS key, then run:

```powershell
$env:KOSIS_API_KEY = "<local-secret>"
python -m alpha_cycle.kosis_industry_discovery_cli
```

or after editable installation:

```powershell
alpha-cycle-kosis-discovery
```

Discovery outputs are written under:

`data/private/live-research/kosis-industry-discovery/`

## Run parameter inventory probe

After table identity is verified, enumerate the latest live classification/item identities:

```powershell
python -m alpha_cycle.kosis_industry_parameter_cli
```

or:

```powershell
alpha-cycle-kosis-parameters
```

The default probe requests the latest monthly period with `objL1=ALL` and `itmId=ALL`. It writes:

- `raw_parameter_data.json`,
- `normalized_rows.json`,
- `parameter_inventory.json`,
- `manifest.json`,
- `latest_kosis_industry_parameters.json`.

Outputs are written under:

`data/private/live-research/kosis-industry-parameters/`

## Bounded history capture

Once exact live classification and item IDs are reviewed, a bounded monthly history can be captured without enabling scoring:

```powershell
python -m alpha_cycle.kosis_industry_parameter_cli `
  --obj "<verified-classification-id>" `
  --itm-id "<verified-item-id>" `
  --start 202001 `
  --end 202606
```

Repeat `--obj` only when the target table requires additional classification dimensions, in `objL1` through `objL8` order.

## Next engineering gates

Only after a live parameter inventory resolves exact semantic identities should the next layers:

1. bind semiconductor-relevant classification IDs and production/shipment/inventory item IDs,
2. fetch bounded monthly histories for those exact IDs,
3. validate units, missing symbols, revisions and publication freshness,
4. derive descriptive production/shipment/inventory diagnostics,
5. add external memory price/supply evidence,
6. outcome-test any proposed cycle policy,
7. keep the signal non-scoring until that research supports a decision rule.
