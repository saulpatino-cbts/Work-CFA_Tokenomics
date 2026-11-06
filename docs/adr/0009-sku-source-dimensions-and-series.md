# 0009. SKU and source dimensions, and bucketed series

- **Status:** Proposed (implemented on the owner's go-ahead for this phase; confirm the rules below)
- **Date:** 2026-11-06
- **Decision authority:** Product owner
- **Owners:** FinOps, Connectors
- **Requirements:** REQ-006, REQ-007
- **Issue:** No issue exists
- **Implementation evidence:** Migration `0004`, `sku`/`source_type` on both observation tables, `GET /v1/usage/series`, `sku`/`source_type` filters on `GET /v1/usage`, and tests against PostgreSQL 16.

## Context

The owner asked for visibility of token type (input, output, cache, reasoning), vendor, and SKU (subscription versus API), fed by enterprise vendor APIs where available. The first dashboard concept was a summary, not telemetry. See [UI concepts](../ui-concepts.md) and [token accounting](../token-accounting.md).

## Decision

- Add two dimensions to every observation. **`sku`**: `api_on_demand`, `api_provisioned`, `subscription` or `unknown`. **`source_type`**: `cloud_telemetry`, `vendor_admin_api` or `app_routed`. `unknown` is the default and is never inferred from a model name; adapters set it only when the source says so.
- The aggregate natural key now includes `sku` and `source_type`, so the same window from two sources is kept as two rows.
- `GET /v1/usage/series` returns one token category per query, bucketed by hour or day, grouped by any of provider (vendor), sku, model and account. **`source_type` is always part of the series key**: sources describing the same traffic are returned as separate series and never added. Within one source, models and windows are disjoint, so they are summed per bucket.
- Provider windows longer than the bucket are counted in `excluded_windows` and left out. A bucket with no data has no point. The response reports the latest window end per provider and source so the UI can mark the not-yet-reported region.
- Account scoping ([ADR 0008](0008-account-scoped-usage-access.md)) applies to series and freshness.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Merge sources into one series | Simpler chart | Double-counts the same traffic | Violates the accounting contract |
| Stack categories into a total | Familiar chart | Providers define cache and reasoning differently | Invalid sum |
| Infer SKU from model or deployment name | Fewer unknowns | Wrong guesses look like facts | Unknown stays unknown |

## Consequences

Chart queries stay read-only and bounded. The ledger can represent subscription SKUs, but subscription usage is stored only if a source reports it; many seat plans are not token-metered. **No vendor admin API adapter exists yet.** Which vendors to ingest, and what each API reports (per key, per project, token types, subscription data), is an open owner decision and must be verified per vendor before an adapter is built.

## Validation

Tests cover source separation, unknown-not-zero, partial flags, window exclusion, SKU filtering, scope enforcement, input validation and migration up/down with existing rows. Not tested: real vendor or cloud data, large volumes, non-UTC day boundaries for customers.

## Rollback or revisit trigger

Reopen if a vendor reports usage that cannot be keyed by these dimensions, or if the owner defines additional SKU types.
