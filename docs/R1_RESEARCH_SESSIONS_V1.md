# Exact R1 research sessions v1

Issue #354 adds durable observation-to-research computation, not forecast linkage
or Product R1 acceptance. Sessions preserve blocked and unavailable results.

## Produce and replay

Use the existing Python 3.12 virtual environment. From the repository root:

```bash
.venv/bin/python -m alpha_cycle.r1_research_cli \
  --research-source SOURCE --store STORE --universe-id reported-actuals --version 1 \
  --field '000660|memory_semiconductor|reported_revenue|CIS:ifrs-full_Revenue#34|2026-06-30|H1' \
  --pack PACK.json
```

`SOURCE`, `STORE` and `PACK.json` are caller-selected paths, not bundled real-data
fixtures. `--pack` is optional; its absence retains model-acquisition blockers.
Existing `--verify-official` behavior remains a separate live operation.

Every successful invocation, including an empty baseline or unchanged comparison,
commits `STORE/research_sessions_v1/<session_id>.json` before printing completion.
JSON output includes `session_id`, `session_path`, and reconstructed `rounds`.
If persistence fails, the invocation fails and the existing current-store failure
publication/CAS rules apply. A competing attempt is reported as `superseded` and
is not overwritten. An already committed universe generation alone is not CLI
research-session success.

For research without a measured change, add:

```bash
--request-member 000660 --request-reason 'Review the baseline evidence and missing drivers'
```

Repeat `--request-member` for other selected members. Requests require unique,
known member IDs and a nonempty reason. They have separate request identities and
`explicit_research_not_measured_discovery` semantics. They never manufacture a
`ResearchCandidate`, triggering change, or candidate lineage. For compatibility,
the existing plan/package `candidate_id` field carries the explicit `request_id`;
the round has a `request` object instead of a `candidate`, and the underlying
plan's `candidate_lineage` is null. A genuine measured candidate can coexist with
an explicit request for the same member, with distinct identities.

Copy the single bundle outside the live store, then replay offline:

```bash
.venv/bin/python -m alpha_cycle.intelligence.research_session_v1 \
  --session ARCHIVE/<session_id>.json
```

Replay does not load a current pointer, acquire provider data, call official
verification, or reissue live authority. It works after a newer success, newer
failure, corrupted current pointer, or removal of the original universe store.
It reconstructs candidates, binding resolutions, plans and packages, comparing
all recorded outputs with their canonical reconstruction before returning.

## Schema and identity

The schema version is integer `1`. The canonical SHA-256 `session_id` covers every
field except itself; the filename must match. Duplicate keys, unsupported schema,
unknown fields in interpreted contracts, and noncanonical outputs are rejected.

| Field | Bound content |
| --- | --- |
| `current_generation` | Exact snapshot ID, manifest ID, attempted timestamp and attempt ID |
| `preceding_attempt` | Successful or failed predecessor, cutoff, failure code and last-success identities |
| `comparison_prior_generation` | Exact parent success used for comparison, or null for initial/recovery baseline |
| `universe_archive` | Ordered complete parent-manifest chain and each exact snapshot's bytes, base64 encoded |
| `candidate_rules` | Full rule definitions, including states, priority, reason and threshold |
| `knowledge_packs` | Complete pack payload/content ID per universe member, including unused baseline inputs; null when absent |
| `binding_policies` | Full driver/source/metric/unit/basis/window/semantics/maximum-age policy per member |
| `explicit_requests` | Member IDs and request reasons, independent of discovery |
| `source_receipts_json` | Canonical, opaque historical receipt record; never parsed as an authority grant |
| `authority_policy` | Fixed recorded-only origin and false live/provider/product authority flags |
| `status`, `snapshot_id`, `cutoff_at`, `changes`, `rounds` | Recomputed outputs, request/candidate, plan/resolution and package IDs, blockers and unavailable states |

The snapshot loader validates every archived manifest's content address, snapshot
byte digest, typed snapshot identity, complete parent ancestry and chronology.
The preceding attempt may select either the exact parent manifest or the
current manifest reused by an identical-snapshot retry. Reuse requires the exact
same snapshot identity and does not manufacture a comparison across equal cutoffs.
The comparison generation remains bound to the preceding successful attempt. Recovery after a failed attempt retains the failed predecessor
and historical success chain, but deliberately makes no comparison across the gap.
Omitting a predecessor cannot disguise a measured change as an initial baseline.

`resolve_research_plan` is the pure resolver shared by historical replay and the
existing `build_persisted_research_plan` wrapper. The wrapper still requires the
current successful store generation and rejects latest failure/stale handoffs.
The pure function itself grants no source authority; archive callers first
validate the manifest-bound inputs.

## Publication and limitations

Publication holds the existing universe writer lock and checks the exact current
attempt. It reuses the immutable writer to stage/fsync complete bytes, then links
the held file descriptor into a descriptor-pinned repository without overwriting
an existing artifact. Identical fixed-generation inputs reuse identical bytes.
A conflicting file is rejected. Partial staging/link failures cannot publish a
partial JSON. Failures after the final link may leave a complete, unannounced
artifact; this is not a successful CLI result or an active current-state claim.

Directory components are opened without following symlinks. File reads reject
symlink leaves, and namespace replacement during publication is rejected. The
current session backend requires POSIX descriptor paths (`/proc/self/fd`) and a
filesystem supporting descriptor-stable hard-link publication. Unsupported
platforms fail explicitly; Windows session publication is not certified here.
Existing non-session platform capabilities are not reclassified by this limit.

A session is a portable copy of the entire successful normalized-universe history,
so size and validation work grow with history. This first schema intentionally
prefers independent replay over deduplicated external archive dependencies.
It does not copy arbitrary external provider raw archives merely referenced by
evidence IDs or receipt paths, or certify their remote origin. Recorded source
receipts may describe historical live verification; reading those bytes never
recreates the process-local live issuance capability. Observation maturity is
inherited unchanged, not independently certified by the session hash.

The v1 replay fixes the computation to this schema/algorithm. No latest-version
pack lookup or implicit migration is allowed. Algorithm changes require a versioned
compatibility decision. Wall-clock CLI reruns create new capture generations;
idempotence applies to the same generation and exact inputs, not different dates.

Tests are explicitly synthetic and writer-backed, including fresh-process replay,
unknown-field and payload/parent tampering, mixed inputs, future evidence,
current-pointer independence, latest failure, recovery, concurrent publication,
partial writes, symlink substitution, and non-escalation of recorded authority.
No fresh financial-data acceptance, forecast accuracy, investment conclusion,
portfolio action, or protected 2026Q3 outcome scoring is claimed by this milestone.

## Review follow-up: attempt reuse and input failures

Attempt predecessors and manifest parents are distinct: the universe writer
reuses a manifest on a same-snapshot retry, including recovery using the last
successful snapshot. Sessions preserve that attempt while producing no invented
change. Other snapshot/parent mixtures remain rejected. Descriptor-link RuntimeError
is translated only at that publication call into a handled failure; unrelated
RuntimeError exceptions are not suppressed. Replay opens with O_NONBLOCK, validates
the opened regular-file descriptor, and checks path identity after reading, so FIFO
inputs and last-moment substitution cannot block the reader.
