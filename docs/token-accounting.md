# Token accounting

**Status:** proposed measurement contract. Validate each field against the selected provider/API/model before implementation. Authentication tokens are secrets; model tokens are usage units. Never put authentication values in the usage ledger.

## Coverage first

| Observation source | Coverage | Limitation |
| --- | --- | --- |
| Application request | Calls actually routed through this application | Does not see external callers. |
| Provider telemetry | Approved provider resource and time window | May be aggregated, delayed, overlapping, or missing user identity. |
| Billing source | Approved reported charges/usage | Different timing, granularity, rates, and adjustments. |

The observation mode is decided in [ADR 0007](adr/0007-observation-mode-and-reconciliation.md): request observations and provider aggregates are both collected and reconciled. Never add application observations and provider totals for the same traffic as separate consumption. Show source, resource scope, freshness, and completeness in the UI.

## Proposed observation model

| Field group | Examples | Rule |
| --- | --- | --- |
| Scope | Installation, workspace, provider account/project/subscription, region | Customer-controlled identifiers; no public disclosure. |
| Model | Provider, endpoint/deployment, model/version, API version | Preserve exact source identity. |
| Grain | Request/attempt ID or aggregate dimensions/window/statistic | Do not fabricate request identity for aggregates. |
| Time | Event/window start/end, ingestion time | UTC with explicit resolution and collection watermark. |
| Usage | Input, output, cache-read/write, reasoning, provider total where supplied | Nullable categories; preserve provider definitions and inclusion rules. |
| Provenance | Source, normalization version, sanitized usage metadata | Exclude credentials and content payloads. |
| Quality | Reported, estimated, partial, unknown, reconciled | Missing is not zero; estimates do not become provider actuals. |
| Cost, if approved | Decimal amount, currency, rate source/version/effective period | Separate estimates, negotiated rates, and reported charges. |

Raw usage metadata means a restricted usage-only field set, not arbitrary request/response bodies. Providers differ in whether categories are nested or additive. A generic sum of every category is invalid. Preserve provider-reported totals and explain mapping differences rather than silently replacing them.

Foundry documents input/output/total metrics; Bedrock has distinct cache categories; Vertex metadata can include cached prompt tokens and thought tokens. See the specific [provider sources](providers.md) before changing normalization rules.

## Deduplication and reconciliation

For request observations, use stable source/request/attempt identity where available. For aggregates, use provider resource, metric, dimensions, window, granularity, and statistic; define replacement/version semantics when a provider revises a window. Do not sum overlapping scopes or windows.

Persist collection checkpoints with durable writes, support safe replay, and retain lineage between source observations and reconciled views. Late arrivals must update the correct window without inflating totals. Import must preserve provenance and deduplication identities.

Each model-call retry may consume usage; preserve attempts rather than recording only the final response. Interrupted streams with missing final usage remain unknown or explicitly estimated. Do not infer a zero charge from a failed request.

## Display and validation

- Distinguish model tokens, API credentials, quota burn, and currency.
- Show incomplete collection and the last successful sync beside totals.
- Attribute per user only when authenticated correlation exists; never infer it from account totals.
- Keep source-specific counts drillable; identical token counts across models are not identical work or price.
- Test cached prompts, reasoning, retries, missing usage, aggregation revisions, overlapping scopes, and replay.

No universal pricing formula, negotiated rate, currency conversion, or billing reconciliation capability is implemented. These require explicit scope and tests.
