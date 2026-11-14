# Retention controls and administrator time zone: design

**Status:** proposal, 2026-11-13, for [ADR 0015](../adr/0015-retention-controls-and-time-zone-setting.md). Nothing here is implemented. It builds on [ADR 0014](../adr/0014-license-support-retention-and-time-zone.md) (retention is the client's choice; UTC with an administrator-chosen zone) and on the customer-owned data boundary in [data ownership](../data-ownership.md). Facts about the current code come from reading `tenancy.py`, the migrations and the models; no new check was run.

## Part A. Time zone

### What exists

Instants are stored in UTC. The parser accepts an `assume_timezone` per import (`--timezone`, default UTC) and records `_assumed_timezone` on each row that needed it. There is no stored setting, and `usage/series.py` buckets by hour or day in UTC.

### Proposal

1. **One tenant setting**, `tenants.timezone` (text, default `UTC`, not null). Valid values are `UTC` or an IANA name. A fixed offset is not allowed here (it cannot follow daylight saving); it stays available per import.
2. **Precedence for a timestamp that carries no zone:** an explicit `--timezone` or connector setting, then the tenant setting, then UTC. A timestamp that states its own offset always wins and is never reinterpreted.
3. **Changing the setting is not retroactive.** Stored rows stay as imported, and the zone assumed for each is already on the row. The change affects future imports and display only. The audit entry records the old and new zone.
4. **Display and buckets.** The API keeps returning UTC instants. The web app formats them in the tenant zone. Day buckets in `usage/series.py` gain an optional zone (`date_trunc('day', ts at time zone :tz)`), defaulting to UTC, so a "day" matches the administrator's day. Billing periods from a source stay as the source states them.
5. **Who:** read for both roles, write for `admin` only, as with `person_display`. Audited as `settings.timezone`.
6. **Dependency:** named zones need the pinned `tzdata` package (already added). An unknown name is refused, never treated as UTC.

### Migration `0012`

`alter table tenants add column timezone varchar(64) not null default 'UTC'`. The zone name cannot be checked in SQL, so the application validates it (`resolve_timezone`) and a short check constraint refuses empty text and whitespace. Downgrade drops the column.

### Tests

Restricted-role write and read; admin-only write; an invalid zone is refused and nothing changes; precedence (explicit beats tenant beats UTC) on an import; a stated offset is never overridden; the audit entry; a day bucket that differs between UTC and a named zone around midnight; changing the setting leaves stored instants untouched.

### Risks

Daylight-saving transitions make some local times ambiguous or non-existent, so a named zone applied to unzoned timestamps carries residual uncertainty (documented; UTC stays the default). Day buckets in a non-UTC zone change what "a day" totals, so the zone used must be shown next to any such figure.

## Part B. Retention controls

### Constraints from the current design

- **Most data tables are append-only for the runtime role** (select and insert only): `value_assumptions`, `calculation_nodes`, `calculation_edges`, `raw_files`, `ingestion_rejects`, `focus_cost_records`, `focus_supersessions`, `allocation_rules`, `allocation_drivers`, `allocated_costs`, `audit_events`, `usage_request_observations`. That protects history. A purge therefore **cannot run as the normal application role**.
- `usage_aggregate_observations`, `usage_facts`, `people`, `ingestion_runs` and others are mutable.
- Calculation nodes are stored with a content hash and reference their inputs, and a tampered stored node is refused. Purging inputs must not break the explain view.
- Deletion is not erasure from backups, logs or archives ([data ownership](../data-ownership.md)). The product must say so and must not promise proof of physical erasure.
- The vendor sets no timer and must not silently choose policy.

### Layers

| Layer | Tables | Notes |
| --- | --- | --- |
| Raw files | `raw_files`, `ingestion_rejects` | Gzipped original exports. Can hold the 1.5 identity columns (R-17). The most sensitive layer and the largest. |
| Cost facts | `focus_cost_records`, `focus_supersessions`, `allocated_costs` | Superseded rows exist alongside current ones. |
| Usage | `usage_request_observations`, `usage_aggregate_observations`, `usage_facts`, `collection_checkpoints` | Checkpoints are never purged (they hold collection position, not history). |
| Calculations | `calculation_nodes`, `calculation_edges`, scenarios | Small, and the explain view depends on them. |
| Audit | `audit_events` | Security record. |
| People | `people` | Pseudonym to name only. |

### Proposal

1. **Policy table `retention_policies`** (one row per tenant and layer): `retain_for` (an interval, or null for "keep"), `archive_first` (boolean), `legal_hold` (boolean), `updated_at`, `updated_by`. **The default is no row, which means keep indefinitely and the UI says "no retention policy set".** The product never invents a period.
2. **A purge is an operator command, not a background timer:** `python -m cfa_tokenomics.admin retention-run TENANT [--layer L] [--apply]`. It is a dry run by default and prints what would go (counts and date ranges per layer, never row content). `--apply` is required to delete. Scheduling is the client's (cron, Azure or AWS scheduler).
3. **A separate database role** `cfa_retention` with `DELETE` only on the tables of layers that have a policy, under row-level security for one tenant. The runtime application role keeps its append-only grants unchanged, so a bug or a stolen application credential cannot delete history. The role is created by the client's database owner with generated grants (like `app-role-sql`).
4. **Legal hold** on a layer blocks every purge of it and is shown prominently.
5. **Archive before delete (optional, per layer).** The cost and raw layers can be written to client-controlled storage (S3 or Blob, through the platform's own identity, as the cost connectors read) before they are removed. The archive format for cost facts is **FOCUS CSV, gzipped**, which this product's importer already reads, so archived months can be re-imported. The archive is the client's, outside the product's control, and the run reports where it went. Parquet is not supported yet (R-27). Other layers need the full export/import, which is not built.
6. **Supersession and totals.** A purge removes whole billing periods (per billing account and sub account), oldest first, never part of a period, and removes the superseded history of a period together with it. This keeps every remaining total internally consistent.
7. **Explain view.** Read from `store.load_node_tree`: the explain tree is rebuilt only from `calculation_nodes` and `calculation_edges` and verified against each node's content hash. Inputs from cost or usage rows are recorded as a `source_ref` on a node, not a database reference, so purging cost, usage or raw rows does **not** break the explain view; the node keeps its figure and its source reference, and the UI can mark that source "expired by retention policy". What would break it is purging *part* of a tree (a missing child raises `missing calculation node`). So the calculation layer must be purged only as whole trees, never node by node.
8. **Audit.** Every run writes an audit event with the policy used, counts per layer, the date range and whether it was a dry run or applied (counts only). Purging the audit layer itself is allowed only with its own policy and `--layer audit`, prints a warning, and the run's own audit entry is written after the purge so it survives it.
9. **What the UI and runbook must say:** deleting here does not remove the data from backups, archives, logs or provider stores, and the product cannot prove physical erasure.

### Migration `0013`

`retention_policies` (tenant, layer, `retain_for`, `archive_first`, `legal_hold`, audit columns; row-level security forced like every tenant table); `retention_runs` (run id, tenant, layer, mode, counts, range, started and finished, actor, archive reference); a function or grants for the `cfa_retention` role. The generated grant SQL lives with `app_role_grants_sql`. Downgrade drops both tables; it does not restore purged data.

### Slices

1. Time zone: migration `0012`, tenant setting, admin API and command, import precedence, zone-aware day buckets, tests. Small and independent.
2. Retention policy storage and dry-run reporting only (no deletes), with tests on counts and legal hold.
3. The `cfa_retention` role, `--apply`, supersession-aware deletes, audit events, and tests that the application role still cannot delete and that the retention role cannot touch another tenant or an unpoliced layer.
4. Archive-before-delete for the cost and raw layers to client storage (needs a real bucket or container to verify).
5. Web screens: retention settings, the "no policy set" state, run history. Brand approval is still pending.

### Not decided here

Whether a client may set a retention shorter than the sources' own revision windows (a purge of a still-revisable period would be reimported by the next run); a minimum for the audit layer; encryption and key custody of archives; and what a restore of older state must do about purged data (data ownership requires honoring prior deletion history).
