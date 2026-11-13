# Test readiness

**Status:** working note, 2026-11-12. Part of the [AI economics redesign](README.md). Everything built so far has been tested on synthetic data only. This note says what real data or access each component needs before it can be called verified, and what to decide first. It records no test result that has not been run.

## 1. Real FOCUS data

The Phase 1 acceptance criterion 1 (import a real FOCUS export and see cost allocated to an application) needs a real export. Two sources exist:

| Source | What it is | Use |
| --- | --- | --- |
| FinOps Foundation [FOCUS-Sample-Data](https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data) repository (public, CC BY 4.0) | Anonymized samples; only a `FOCUS-1.0` folder was found | Parser and import testing. Not stored in this repository. |
| An export from a test or CBTS-owned AWS or Azure account, run through `python -m cfa_tokenomics.sanitize` | The only real evidence for the cost connectors | Needs an owner decision on which account. |

No MCP server for the FinOps Foundation is available in this environment, so the public repository was read with the GitHub API.

### Probe result (2026-11-12, run, not assumed)

The 1,000-row `focus_sample.csv` (FOCUS 1.0 layout, about 755 KB) was run through the strict parser (`parse_focus_csv`) with the declared version `unknown` and `1.0`. Both gave the same result: **0 rows accepted, 1,000 rejected**.

| Rejection | Rows | Cause |
| --- | --- | --- |
| `timestamp_without_timezone` on `ChargePeriodStart` | 993 | The file writes `2024-09-18 22:00:00` with no timezone marker. The importer refuses to guess a timezone. |
| `not_a_number` on `ContractedCost` | 7 | Non-numeric text where a number is required. |

The `ProviderName` alias to `ServiceProviderName` was applied, and `PublisherName` and `Id` were reported as unknown columns. The larger 10,000 and 100,000 row files were not tested (the 10,000 row download failed in transit).

Reading: the importer's refusal to coerce was working as designed, but real files do not match its strictness. The owner decided on 2026-11-12: **read an unzoned timestamp as UTC unless the administrator chose another zone** ([ADR 0014](../adr/0014-license-support-retention-and-time-zone.md)).

### After the fix (run, not assumed)

The parser now reads an unzoned timestamp as UTC by default (a zone stated in the file is never overridden), records the assumption on each affected row, accepts `UTC`, fixed offsets and named zones, treats an unknown zone as an error, and keeps the old strict behaviour available. It also reads the literal `NULL` in optional number, timestamp and JSON columns as unknown (never zero); a required column holding `NULL` is still rejected. Re-running the same 1,000-row sample: **993 rows accepted, 7 rejected** (a required `ContractedCost` of `NULL`, which is correct to reject). `tests/test_focus_parse.py` passes (45 passed, 1 skipped; the skip is the named-zone test, which needs the `tzdata` package that is pinned in `pyproject.toml` but not installed on this machine). The database-backed importer and connector tests could not run on this machine, but the pull request's CI run (PostgreSQL 16, ruff, 544 tests then 545 with the rehearsal below) passed them, including the named-zone test.

Not done: the per-tenant administrator time zone setting (today the zone is chosen per import with `--timezone`) and the larger 10,000 and 100,000 row samples.

## 2. Connector readiness

None of the four connectors has run against a real service. "Do they work for what we need?" is unknown until one has. The need is: cost and usage per application, with provenance, as the product defines it. A connector only automates fetching; the manual FOCUS import already covers the cost side. So the cheapest first evidence is a real export imported by hand, and a connector test comes second.

| Connector | Needs before a test | Known uncertainty | Risk |
| --- | --- | --- | --- |
| AWS Data Exports | A FOCUS export in S3 in a test account (AWS offers FOCUS 1.2 and 1.0), and a read-only role the connector can use through the platform's identity | Real manifest timing, file sizes, column set; an export above the in-memory cap (default 200 MB) is refused | R-27 |
| Azure Cost Management | An export to Blob storage and a reader identity (managed identity) | Azure's FOCUS export was still 1.2-preview when last found; layout unverified | R-27 |
| Anthropic | An organization with an Admin API key (read-only) | The Admin usage and cost analytics API is beta; live encoding of `group_by[]`, paging and rate limits unverified; `BilledCost` is pre-credit | R-29 |
| Codex / ChatGPT Enterprise | An Enterprise workspace and an Admin key (read-only) | Live paging, rate limits and the correction window unknown (30 days assumed); credit-priced cost is an estimate | R-30 |

**Go or no-go before spending effort:** for each, decide whether CBTS or a pilot client actually has that vendor account. Without the account there is nothing to test and the connector should wait. Ask the client what they use before testing a connector for a vendor they do not have.

## 3. Migration rehearsal (R-26)

Migration `0008` adds a tenant to the older tables (roles, grants, audit, usage observations). If an installation already holds rows from before that migration, those rows have no tenant, stay invisible, and `/readyz` reports `legacy_tenant_unassigned` until an operator runs `python -m cfa_tokenomics.admin assign-legacy-tenant TENANT_ID`. An empty install is finalized by the migration itself.

**Done (2026-11-13, in CI on PostgreSQL 16, synthetic data):**

- `tests/test_legacy_isolation.py` already covered the mechanics with one row per table: old rows invisible until assigned, assignment finalizes, downgrade round trip, refusal to merge tenants that share a key, `/readyz` states.
- New `tests/test_migration_rehearsal.py` adds volume: it builds a pre-tenancy install, fills every legacy table with 20,000 synthetic rows (`CFA_REHEARSAL_ROWS` changes this), upgrades, assigns a tenant, and checks that row counts match before and after, no row is left without a tenant, the tenant sees every row, another tenant sees none, and a second assignment does nothing. It also checks that migration `0010` folded the old `user` and `reader` roles into `finance_viewer`. It passed in CI (545 tests passed, none skipped). Timings are printed by the test but were not captured from CI, so no duration is claimed here.

**Not done:** a rehearsal on a copy of a *real* install, which is what closes R-26. Nothing in a synthetic run shows how long it takes on real volumes or whether real data holds anything the synthetic rows do not. With one client per install and no install holding data yet, that remains dormant until the first real install is upgraded.

## 4. Real identity provider test

Deliberately last (milestone 5 in the [roadmap](../roadmap.md)). Entra ID first, Google Workspace second.

## 5. Suggested order

1. Done: timestamp rule (section 1). Fabricate fuller synthetic data towards the end of the beta, using the FOCUS template information; a real export remains needed for acceptance.
2. Import the real export by hand; allocate it to one application; compare allocated plus unallocated to the line totals.
3. Confirm which vendors the first client uses; test only those connectors.
4. First install from a marketplace or standalone package; rehearse the migration on it before its first upgrade.
5. Real IdP test.
