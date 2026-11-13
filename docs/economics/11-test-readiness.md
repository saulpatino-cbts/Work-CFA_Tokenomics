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

Reading: the importer's refusal to coerce is working as designed, but real-world files may not match its strictness. **Owner decision needed:** keep strict and require sources to emit timezone-marked timestamps (`--allow-partial` would only skip the rejected rows, so a file like this would import nothing), or add an explicit, recorded, per-source option that declares the timezone of a timestamp that lacks one (for example "treat as UTC"). Nothing was changed in the parser. The second option would be a new documented behaviour, not a silent fix.

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

A rehearsal means doing that on a copy of a real install that has data, comparing row counts before and after. Since every install is for one client and no install with data exists yet, **this risk is dormant**. It becomes live the first time an existing install is upgraded. It can wait until a first real install exists, and should happen before that first upgrade.

## 4. Real identity provider test

Deliberately last (milestone 5 in the [roadmap](../roadmap.md)). Entra ID first, Google Workspace second.

## 5. Suggested order

1. Owner chooses the timestamp rule (section 1) and the source of the first real export.
2. Import the real export by hand; allocate it to one application; compare allocated plus unallocated to the line totals.
3. Confirm which vendors the first client uses; test only those connectors.
4. First install from a marketplace or standalone package; rehearse the migration on it before its first upgrade.
5. Real IdP test.
