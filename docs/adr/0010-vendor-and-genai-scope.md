# 0010. Vendor and Gen AI scope

- **Status:** Accepted (owner-stated scope, 2026-11-06); no adapter implemented, all API capabilities unverified
- **Date:** 2026-11-06
- **Decision authority:** Product owner
- **Owners:** Connectors, FinOps
- **Requirements:** REQ-006, REQ-007
- **Issue:** No issue exists
- **Implementation evidence:** Pending. The ledger can already represent these sources ([ADR 0009](0009-sku-source-dimensions-and-series.md)); no connector exists for any vendor named here.

## Context

The owner stated the target scope for the first enterprise customers. It extends [providers](../providers.md), which listed only Foundry, Bedrock and Vertex AI. This record states the scope; it does not state what any vendor API provides.

## Decision

Three groups, each with its own ingestion route:

1. **Agentic AI vendors, via the vendor's own API** for billing and token usage: Claude Code, OpenAI Codex, Perplexity, Google Gemini and GitHub Copilot. Source type `vendor_admin_api`.
2. **Cloud AI platforms, via cloud APIs and connectors:** AWS Bedrock, Microsoft Foundry and Google Vertex AI. Source type `cloud_telemetry`. Expected to be easier because the data is cloud-hosted.
3. **Gen AI productivity: Microsoft Copilot.** Needs Microsoft Viva and Microsoft Graph integration, and must account for licensing (license assignment and utilization). Mostly the `subscription` SKU, and seat plans are often not token-metered, so tokens stay "not reported" unless a source supplies them.

Rules that follow from the ledger:

- Vendor ids are opaque strings; adding a vendor is an adapter, not a schema change.
- **Overlap is expected.** A model used through a cloud platform can also appear in the model vendor's own usage API (for example Claude through Bedrock). The sources are kept apart and never added; the UI shows one source at a time.
- Per-user figures need authenticated correlation from the source. Microsoft Copilot data can identify individuals, so it needs a privacy review before ingestion (see risk R-17 in the [risk register](../risk-register.md)).

## Open items before any adapter (all unverified)

For each vendor: which API reports usage and billing, authentication and the permissions it needs, token categories and their definitions, grain (per key, project, user, seat), delay and revisions, rate limits, and whether subscription use exposes anything beyond seat counts. For Microsoft Copilot: the Graph and Viva reports available, required admin roles and consent, license reporting, and retention. Vendor documentation must be read for each before an adapter is designed.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Cloud platforms only | Easiest data | Misses agentic and productivity spend | Owner scope |
| One generic "vendor" adapter | Less code | Vendors differ in grain, auth and semantics | Per-vendor adapters behind one contract |

## Consequences

Large integration surface and per-vendor credentials, all customer-held ([ADR 0001](0001-customer-hosted-boundary.md)). Customer admins need clear permission checklists per source. Some vendors may expose too little to support token charts; the UI must say "not reported" rather than imply zero.

## Validation

Each adapter needs sanitized fixtures from documented responses, contract tests, and an authorized integration test. None exist.

## Rollback or revisit trigger

Reopen per vendor if its API cannot supply usage at a useful grain or its terms forbid the intended use.
