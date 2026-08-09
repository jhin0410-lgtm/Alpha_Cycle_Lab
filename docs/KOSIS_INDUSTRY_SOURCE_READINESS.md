# KOSIS Industry Source Readiness

## Purpose

This layer discovers the official KOSIS table identity needed for a future Korean semiconductor production/shipment/inventory cycle signal. It does **not** certify the semiconductor industry cycle and does **not** change the investment decision score.

Target table title:

`품목별 광공업 생산·출하·재고·내수·수출량`

Default organization ID:

`101` (official KOSIS statistics provider scope used by the target survey)

## Official API contracts

The implementation uses only the HTTPS KOSIS OpenAPI host:

- Integrated search: `https://kosis.kr/openapi/statisticsSearch.do?method=getList`
- Table metadata: `https://kosis.kr/openapi/statisticsData.do?method=getMeta&type=TBL`
- Future parameter data: `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`

The API key is loaded from local `KOSIS_API_KEY` and is never written into discovery artifacts.

## Current certification boundary

The discovery command verifies only:

1. official KOSIS host,
2. integrated-search result identity,
3. exactly one exact Korean table-title match,
4. table-title agreement with the independent table metadata endpoint,
5. immutable raw search and metadata response hashes.

Every artifact explicitly records:

- `industry_cycle_certified=false`
- `decision_score_enabled=false`

If there are zero or multiple exact matches, discovery remains uncertified.

## Why table identity is not enough

The KOSIS parameter-data endpoint requires explicit table, classification and item identifiers (`orgId`, `tblId`, `objL1...objL8`, `itmId`, `prdSe`). These identifiers must be verified from the live official metadata/table before any production, shipment or inventory series is interpreted.

The parameter-data response can include `LST_CHN_DE` (last modification date). That field will be retained in future raw evidence, but it must not be treated as a complete historical vintage database. Historical backtests therefore remain revision-sensitive unless archived vintages are independently available.

KOSIS alone can support a narrowly scoped Korean mining/manufacturing production-shipment-inventory cycle view. It is not sufficient to certify the broader memory-semiconductor cycle, which also needs memory price and supply evidence.

## Run discovery

Set a local KOSIS key, then run:

```powershell
$env:KOSIS_API_KEY = "<local-secret>"
python -m alpha_cycle.kosis_industry_discovery_cli
```

or after editable installation:

```powershell
alpha-cycle-kosis-discovery
```

Outputs are written under:

`data/private/live-research/kosis-industry-discovery/`

The latest pointer is:

`latest_kosis_industry_discovery.json`

## Next engineering gate

Only after a live discovery artifact resolves one verified table identity should the next layer:

1. discover/verify exact classification and item codes,
2. fetch a bounded monthly history,
3. preserve raw KOSIS responses and `LST_CHN_DE`,
4. validate units, duplicate keys, missing symbols and publication freshness,
5. derive descriptive production/shipment/inventory diagnostics,
6. keep the signal non-scoring until outcome research supports a decision policy.
