# 4. Connector framework

**Status:** proposed. Part of the [AI economics redesign](README.md). The capability matrix is drawn from vendor documentation read on 2026-11-07. Items the pages did not state are marked **not found**; items from truncated pages are marked **(summary)**. Re-verify each source before building its connector, because these APIs change (several are in beta).

## Principles

1. **Land raw first.** A connector returns unmodified payloads plus metadata. A separate, versioned, pure **mapper** turns raw into normalized facts, so history can be re-mapped without re-pulling.
2. **Declare what you can measure.** A connector publishes a manifest of measures, grains, delays and permissions. The product never assumes token telemetry exists.
3. **All provider logic lives here.** No business logic branches on a vendor.
4. **Server-side only, least privilege, read-only.** Credentials are secret-store references resolved by workers. No credential reaches the browser, a log or a raw payload.
5. **Minimize on ingest.** Drop what the product does not need (prompt and response bodies, user names) before landing, or pseudonymize it.
6. **Be honest about time.** Record each source's delay and revision window; mark facts `provisional` until it closes.

## Contract

```text
Connector
  manifest()                          -> Manifest      measures, grains, delay, revision window, auth kind,
                                                       required permissions, rate-limit notes, FOCUS version emitted
  validate_credentials(ref)           -> CredentialStatus
  discover(ref)                       -> Scope[]       accounts, subscriptions, projects, workspaces, resources
  pull(scope, window, cursor)         -> RawBatch      payload refs + content hash + next cursor + completeness
Mapper (versioned, pure, no I/O)
  map(raw, scope, mapper_version)     -> Usage[], Cost[], Resource[], with basis and finality set
```

Rules: `pull` is idempotent for a window; the cursor advances only after the raw batch is durably stored; partial data is flagged and does not advance the cursor; every request uses bounded retries with backoff and honors the source's rate limits (several limits are **not found** in the documentation, so none is assumed); mappers never call out, so replay is deterministic.

**Registry and onboarding.** A connector registers its manifest. The UI shows the permission checklist, runs `validate_credentials`, then `discover`, then a dry-run `pull`, and reports each step separately (identity, network, access, data), as the earlier setup design intended.

**Health.** Per connector: credential status, last success, lag versus the manifest's expected delay, last error class, rows ingested, schema drift (unexpected fields), and permission over-grant where inspectable. Surfaced on a health screen and alertable.

**Manual import is a first-class connector.** It accepts FOCUS files (CSV or Parquet, any version from 1.0), a generic CSV with a saved column mapping, and a usage template. It is the fastest route to real data, the fallback for sources with no API, and the way customers supply price sheets and invoices.

## Manual FOCUS import (implemented)

`python -m cfa_tokenomics.admin import-focus TENANT_ID FILE [--version 1.2] [--final] [--allow-partial]` imports a FOCUS CSV (plain or gzip) through a connector named `manual-focus-import`. It is the first connector and the way to put real cost data into the model before any API connector exists. **Tested on synthetic files only; no real export has been imported.**

- **Parse, don't coerce.** Required columns are the five FOCUS-mandatory ones (`BilledCost`, `EffectiveCost`, `ListCost`, `ContractedCost`, `ChargeCategory`) plus `ChargePeriodStart`, `ChargePeriodEnd` and `BillingCurrency`. A row is rejected, with a reason code, for an unknown `ChargeCategory`, a non-finite or non-numeric amount, an amount with more than 18 decimal places (never rounded), a timestamp without a time zone, a bad currency code, an empty period, or invalid tags. Unrecognized columns (for example Azure's `x_` columns) are kept as extensions.
- **Strict by default.** If any row is rejected the whole file is refused and nothing is imported (the rejects are recorded). A partial import silently drops money, and a later revised export would then replace good earlier rows. `--allow-partial` is explicit consent.
- **Once per file.** The same file content is imported once per connector.
- **Revisions replace, never add.** A revised export supersedes earlier records only for the (billing account, sub account) pairs it contains and only inside the charge-period window it covers; replaced rows stay as history. Different connectors are different sources and never supersede each other. This rule is a working design and **needs checking against real Azure and AWS exports** (partial or filtered exports could behave differently).
- **Finality.** A run is `provisional` until its last charge period ended more than 7 days ago, then `final` (Azure documents changes until the fifth day after period end; Anthropic reports about a week). `--final` overrides.
- **Lineage.** Every record points to its raw file (kept gzip, byte for byte) and its row number. Cost records, raw files, rejects and supersessions are append-only.
- **Version.** The declared FOCUS version (1.0 to 1.5) is recorded but processing is by column name. `ServiceProviderName` is required for declared 1.4 and 1.5 (Mandatory in 1.4). The only legacy mapping is `ProviderName` to `ServiceProviderName` (confirmed from the specification history), recorded in the row when used; `PublisherName` is kept as an extension. See [FOCUS 1.5 readiness](08-focus-1-5-readiness.md).
- **Privacy.** The 1.5 identity columns are not stored in normalized records unless explicitly requested. The raw file is kept as received.
- **Currency.** `BillingCurrency` must be a three-letter code; `PricingCurrency` may be a provider unit (FOCUS 1.5 draft).
- **Not built:** Parquet (Azure and AWS can export it) and automatic version detection.

## Capability matrix

`Tokens` means token counts by category. `Cost` means a dollar amount from the source. `Seats` means seat or licence data.

| Source | Tokens | Other usage | Cost | Seats and licences | Authority for cost |
| --- | --- | --- | --- | --- | --- |
| **AWS Data Exports (CUR 2.0 and FOCUS)** | no (usage amounts in billing lines) | resource and usage lines | **yes, billed** | no | **Billed cost** for AWS services including Bedrock |
| **AWS Bedrock CloudWatch** | **yes** | invocations, latency, errors, throttles | no | no | none (usage driver) |
| **AWS Bedrock invocation logs** | **yes, per request** | requests | no (cost is an estimate from tokens and your rate card) | no | none; **contains full bodies** |
| **AWS Cost Explorer API** | no | cost by dimension | yes | no | not established: granularity, history and pricing **not found** |
| **Azure Cost Management export (FOCUS)** | no | usage lines | **yes, billed and amortized** | no | **Billed cost** for Azure services |
| **Azure OpenAI / Foundry metrics** | **yes** | requests | `FoundryModelEstimatedCost` is an **estimate (preview)** | no | none; estimate only |
| **Anthropic Usage and Cost Analytics API** | **yes** | requests | **yes** (`amount`, `list_amount`) | no | Vendor cost, when billed by Anthropic |
| **Anthropic Claude Code Analytics API** | **yes** | sessions, accepts, commits, PRs | `estimated_cost` | no | none (estimate) |
| **GitHub Copilot usage metrics** | partial (CLI, app, BYOK fields) (summary) | interactions, active users, acceptances | no | no | none |
| **GitHub Copilot seats and billing** | no | AI credits (premium requests were replaced on 2026-06-01) | **yes** (`netAmount` etc.) | **yes** (seats, plan, last activity) | **Billed cost** from GitHub |
| **Microsoft 365 Copilot (Graph reports)** | **no** | active users, prompt counts, per-app last activity | **no** | licensed users only; licensing via Graph | none |
| **Microsoft Graph licensing** | no | no | no | **yes** (`consumedUnits`, per-user license details) | none (needs a licence price) |
| **OpenAI Usage and Costs API** | **yes** | requests | **yes** (daily only) | no | Vendor cost |
| **OpenAI Codex (workspace analytics)** | **not found** (a Daily Usage Analytics API exists; its fields were not readable) | daily usage | not found | not found | not established |
| **Google Gemini and Vertex AI** | Vertex: token metrics in Cloud Monitoring (beta). Gemini Developer API: per response only, no org API found | n/a | via Cloud Billing | no | Cloud Billing BigQuery export (a FOCUS export is in preview) |
| **Perplexity** | per response only; no org API found | console only | console only | no | not established |
| **Application and gateway telemetry** | **yes, per request** (if instrumented) | requests, sessions, users | no | no | none |
| **Manual import** | as supplied | as supplied | as supplied | as supplied | as supplied |

### Source notes

The notes below were the first reading. The later, fuller research (nine vendors, with sources, permissions, limits, privacy flags and the items still not found) is in [vendor API research](09-vendor-api-research.md); where the two differ, **that document is current**. Its main corrections: Claude in Azure Foundry is billed through one Marketplace consumption-unit meter; third-party Bedrock models are billed under the model provider, not under Bedrock; GitHub replaced premium requests with AI credits and retired its legacy metrics APIs; OpenAI cost amounts are JSON numbers, not strings; and Microsoft Copilot reports now exist under `/copilot/reports` in v1.0.

**Anthropic.** Current API is in beta: `GET /v1/organizations/analytics/usage` and `.../analytics/cost` with the header `anthropic-beta: analytics-usage-cost-2026-08-24`; a legacy `usage_report/messages` endpoint is still documented. Auth is an Admin API key or an OAuth token with the `org:admin` scope (Console organizations), or a key with the `read:analytics` scope (Claude Enterprise); unavailable to individual accounts. Token categories: uncached input, cache creation (5-minute and 1-hour), cache read, output, total, plus requests and web-search requests. Dimensions: model, workspace, API key, actor (user, service account or key), service tier, context window, inference geography, speed, product; up to five `group_by` values. Buckets `1m`, `1h`, `1d`; at most 31 days per request. Cost amounts are **decimal strings in cents with six decimals** (parse as decimal, never float), always USD. Data typically refreshes within 4 hours and can take up to 24; values can be revised until about 7 days after month end; responses carry `data_refreshed_at`. Claude Code Analytics (`/v1/organizations/usage_report/claude_code`) is one UTC day per request, includes user email, and **does not return subscription-plan usage** (Pro, Max, Team, Enterprise); only usage authenticated against the Console organization. (<https://platform.claude.com/docs/en/manage-claude/usage-cost-analytics-api>, <.../claude-code-analytics-api>)

**GitHub Copilot.** Usage-metrics report endpoints exist at enterprise and organization level (`.../copilot/metrics/reports/...`, 1-day and 28-day, by users, repos, teams); responses are download links to signed report files; the enterprise policy "Copilot usage metrics" must be enabled; history from 2025-10-10 up to one year. Seat endpoints (`/orgs/{org}/copilot/billing`, `.../billing/seats`) return seat counts, plan type and last activity (owners only). Billing endpoints (`/organizations/{org}/settings/billing/premium_request/usage`, `.../ai_credit/usage`, `.../usage`) return product, SKU, model, unit type, price per unit, gross and net amounts; org administrator required; last 24 months. No dollar-cost field in the metrics reports; token fields only in some CLI and app breakdowns (summary). (<https://docs.github.com/en/rest/copilot/copilot-usage>, `.../copilot-user-management`, `.../billing/usage`)

**Microsoft 365 Copilot.** Graph function `getMicrosoft365CopilotUsageUserDetail` (path `GET /v1.0/copilot/reports/...(period='D7')`; periods D7 to D180 and ALL) returns per-user last-activity dates per app and, in v2, prompt counts and active usage days; CSV or JSON; **licensed Copilot users only**; permission `Reports.Read.All`. **No tokens and no cost.** By default user-identifying fields are hidden in usage reports; data appears within about 48 hours. Licensing: `GET /subscribedSkus` (`consumedUnits`, `prepaidUnits`) and `GET /users/{id}/licenseDetails`, permission `LicenseAssignment.Read.All`. The Copilot SKU name and the Viva Insights Copilot Dashboard were **not read**. (<https://learn.microsoft.com/en-us/graph/api/reportroot-getmicrosoft365copilotusageuserdetail?view=graph-rest-beta>, `.../subscribedsku-list`)

**Azure.** Cost Management exports include "Cost and usage details (FOCUS)" (documented as 1.2-preview) for EA and MCA scopes; management-group scope is not supported; delivery to a storage account as CSV or Parquet with a manifest per run; typically available within 4 hours of a run, with charges changing until the fifth day after period end and rerating until invoice close. About 52 `x_` Azure-specific columns. RBAC: Cost Management Reader (view), Cost Management Contributor (create exports; "recommended least privilege role"), plus Storage Account Contributor for export storage; Monitoring Reader for metrics. Azure OpenAI metrics: `ProcessedPromptTokens`, `GeneratedTokens`, `TokenTransaction`, `InputTokens`, `OutputTokens`, `TotalTokens`, `AzureOpenAIRequests`, cache and PTU metrics; dimensions include deployment, model, version, region; 1-minute grain. `FoundryModelEstimatedCost` is explicitly "an estimate and is not an invoice or billed charge". **No documented join between token metrics and Cost Management rows** other than shared resource tags. Numeric API rate limits were **not found**. (<https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports>, `.../dataset-schema/cost-usage-details-focus`, `.../foundry-classic/openai/monitor-openai-reference`)

**AWS.** Data Exports offers "FOCUS 1.2 with AWS columns", "FOCUS 1.0 with AWS columns" and CUR 2.0 to S3 (ZIP, GZIP, Parquet); finest grain is per usage type per day. Bedrock publishes CloudWatch metrics in `AWS/Bedrock`: `Invocations`, `InputTokenCount`, `OutputTokenCount`, `CacheReadInputTokenCount`, `CacheWriteInputTokenCount`, latency, error and throttle metrics, `EstimatedTPMQuotaUsage` (an approximation; "do not use as the sole indicator"), dimension `ModelId`. **Invocation logging** is off by default and records, per request, `accountId`, `region`, `requestId`, `modelId`, `identity.arn`, `inputTokenCount`, `outputTokenCount`, `requestMetadata`, and **full input and output bodies** (up to 100 KB). **Attribution:** application inference profiles carry tags that flow to Cost Explorer and CUR once activated as cost allocation tags (up to 24 hours; not retroactive); per-request metadata appears only in invocation logs and **not** in Cost Explorer or CUR, so cost derived from logs is an estimate. Latency and restatement behaviour of Data Exports, CloudWatch and logs were **not found**. (<https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring-runtime-metrics.html>, `.../model-invocation-logging.html`, `.../cost-mgmt-application-inference-profiles.html`, `.../cost-mgmt-request-metadata.html`)

**OpenAI.** Organization usage endpoints (`/organization/usage/completions`, `/embeddings`, `/images`, and others) and `/organization/costs`, authenticated with an admin key. Completions report `input_tokens` ("including cached and cache-write tokens"), `output_tokens`, `input_cached_tokens`, `input_uncached_tokens`, `input_cache_write_tokens`, request counts; grouping by project, user, API key, model, batch, service tier. Buckets `1m`, `1h`, `1d`. Costs: daily buckets only (summary). Data delay and retention **not found**. Codex: a daily usage Analytics API exists for ChatGPT and Codex workspaces and requires a workspace-scoped admin key with a specific scope; its endpoints and fields were **not read**. (<https://developers.openai.com/api/reference/resources/organization/subresources/usage>)

**Google Gemini and Perplexity.** Gemini returns per-response `usageMetadata` (prompt, cached content, candidates, tool use, thoughts, total; `promptTokenCount` **includes** cached tokens). No organization usage API was found in the pages read; costs are in Cloud Billing, which can lag about a day. Perplexity documents an admin-only console usage page and a per-response `usage.cost.total_cost`; **no organization usage API was found**. Vertex AI, Cloud Billing export and Cloud Monitoring were **not read**.

## Consequences for the design

- **Cost authority belongs to billing sources**, not usage sources. Bedrock and Azure OpenAI tokens *explain and allocate* cost that arrives in CUR or the Azure FOCUS export. Estimates from tokens times a rate card are `estimated` and never replace billed cost ([overlap resolution](05-calculation-engine.md#10-overlap-resolution)).
- **Where the product is the bill, use the vendor's cost.** Anthropic and OpenAI cost endpoints are observed vendor cost, *unless* the model is bought through a cloud marketplace, in which case the cloud invoice is the billing owner.
- **Subscriptions have cost without tokens.** Copilot seats cost `seats × price` (billing API, invoice import or price book) and report activity, not tokens. Their unit economics are per seat, per active user or per prompt. The UI shows tokens as "not reported", never zero.
- **Allocation needs tags.** Azure resource tags, AWS cost allocation tags and Bedrock application inference profiles are the documented attribution routes; per-request metadata is estimate-only. The product recommends tagging conventions and reports allocation coverage.
- **Privacy by design.** Several sources return per-user data (Anthropic actor email, GitHub per-user reports, M365 per-user rows) and Bedrock logs hold prompt bodies. Defaults: ingest aggregates, pseudonymize user references, never ingest bodies, and put retention on every layer. This is risk R-17.
- **Versions and revisions differ per source**, so facts carry `finality` and the FOCUS source version.

## Adding a provider

1. Read the vendor's documentation; fill a manifest and record anything *not found* as unknown.
2. Write sanitized fixtures from documented responses (never customer data).
3. Implement `pull` and a pure mapper; set `basis` and `finality`.
4. Contract tests: idempotent window, cursor safety, partial data, mapper determinism, no secret or body in raw or logs.
5. Document required permissions and the onboarding checklist.
6. An authorized integration test in a customer or test account before the connector is marked supported.

No provider requires a schema or business-logic change.
