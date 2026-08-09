# KOSIS Discovery Status

Status: `quantity_table_valid_but_semiconductor_primary_rejected`

## Live results established on 2026-08-09

The official KOSIS quantity table was successfully discovered and queried:

- organization ID: `101`
- table ID: `DT_1F02012`
- title: `품목별 광공업 생산·출하·재고·내수·수출량`
- strict JSON mode: `jsonVD=Y`
- latest parameter probe period: `202606`
- returned rows: `330`
- returned classifications: `66`
- returned item IDs: `5`
  - `T40`: 품목별생산량
  - `T41`: 품목별출하량
  - `T42`: 품목별재고량
  - `T43`: 품목별내수량
  - `T44`: 품목별수출량
- semiconductor classification matches: `0`

This is a useful negative result. The table identity and ingestion path are valid, but the live inventory does not support treating `DT_1F02012` as the primary semiconductor-cycle source.

The original inventory schema also summarized one unit per item even though units can vary by classification. Inventory schema v2 now preserves every observed unit variant per item instead of presenting one representative unit as universal.

## Corrected semiconductor source targets

The next primary KOSIS candidates are:

1. `시도/산업별 광공업생산지수(2020=100)`
   - intended role: semiconductor production / shipment / inventory industry indexes
   - required semantic gate: a verified `반도체 제조업` classification
2. `제조업 생산능력 및 가동률지수(2020=100)`
   - intended role: semiconductor production-capacity / utilization context
   - required semantic gate: a verified semiconductor classification

The repository contains a new source-discovery command that performs, for both candidates:

1. exact integrated-search table match,
2. independent table-title metadata verification,
3. latest monthly `objL1=ALL`, `itmId=ALL` parameter probe,
4. item/unit inventory capture,
5. semiconductor classification-name verification.

Run:

```powershell
python -m alpha_cycle.kosis_semiconductor_source_discovery_cli
```

or after installing the project entrypoint:

```powershell
alpha-cycle-kosis-semiconductor-sources
```

## Certification boundary

All KOSIS artifacts remain:

- `revision_sensitive=true`
- `historical_vintage_certified=false`
- `industry_cycle_certified=false`
- `decision_score_enabled=false`

No KOSIS industry-cycle evidence is allowed to affect investment scoring until exact semiconductor classifications, item IDs, bounded monthly histories, revision/freshness checks, and outcome research are complete.
