# KOSIS Discovery Status

Status: `live_table_identity_verified_parameter_ingestion_ready`

Established from the live official KOSIS service on 2026-08-09:

- organization ID: `101`,
- table ID: `DT_1F02012`,
- exact table title: `품목별 광공업 생산·출하·재고·내수·수출량`,
- table identity status: `table_identity_verified`,
- strict JSON mode requirement: `jsonVD=Y`.

The repository now also contains a read-only parameter-data ingestion layer for:

`https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`

The default parameter probe requests:

- `objL1=ALL`,
- `itmId=ALL`,
- `prdSe=M`,
- latest one published period only.

Its purpose is to enumerate the live classification IDs, item IDs, units and source revision dates before any series is interpreted as an industry-cycle signal.

Captured parameter artifacts preserve raw and normalized payload hashes and explicitly record:

- `revision_sensitive=true`,
- `historical_vintage_certified=false`,
- `industry_cycle_certified=false`,
- `decision_score_enabled=false`.

Still not established:

- exact semiconductor-relevant classification and production/shipment/inventory item IDs from a live parameter probe,
- bounded monthly histories for those verified IDs,
- point-in-time historical vintage certification,
- memory price/supply evidence,
- an outcome-tested industry-cycle scoring policy.

Therefore KOSIS evidence remains descriptive and non-scoring until those gates are completed.
