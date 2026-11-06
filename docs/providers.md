# Provider integrations

**Status:** required integrations; no connector is implemented or verified yet. Provider, model, API, region, and authentication support must be explicitly versioned in the implementation.

## Capability boundaries

| Capability | What it establishes | What it does not establish |
| --- | --- | --- |
| Credential validation | Identity can authenticate to the tested endpoint | Model access, telemetry, or billing permission. |
| Model access check | Selected model/API is reachable and permitted | Visibility of traffic made outside this app. |
| Telemetry collection | Authorized metrics/logs within a configured scope | Universal per-user attribution or complete account billing. |
| Request usage capture | Usage returned for requests routed through this app | All usage in the customer's environment. |
| Optional billing ingestion | Approved billing data with its own cadence | A real-time per-request ledger. |

A connection needs separate health results for identity, network, model access, telemetry, and optional billing. Customers may configure any subset of providers. Do not require all three to finish setup.

## Vendor scope extension

The owner extended scope to Claude Code, OpenAI Codex, Perplexity, Google Gemini and GitHub Copilot via their own APIs, and Microsoft Copilot via Microsoft Graph and Viva. See [ADR 0010](adr/0010-vendor-and-genai-scope.md). **None of these is implemented or verified**; each needs its documentation read and its fields confirmed first.

## Foundry

Support customer-approved Entra/workload identity or supported API-key authentication through customer-local configuration. Define the exact Foundry endpoint/service and deployment type; do not assume all endpoints expose identical APIs or telemetry.

Azure Monitor documents input/output/total token metrics with model/deployment/region dimensions. Do not invent an end-user dimension or label aggregate observations as individual requests. See [Foundry monitoring](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/monitor-models).

## Bedrock

Separate inference permissions from CloudWatch/telemetry and optional billing permissions. Prefer scoped temporary workload credentials where supported; if Bedrock API keys are supported, document their lifetime, API coverage, and restrictions rather than treating them as universal AWS credentials.

Bedrock runtime metrics include input/output and cache read/write categories. Preserve their documented meanings and dimensions. Quota consumption is not the same as billed usage. See [Bedrock runtime metrics](https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring-runtime-metrics.html) and [API-key scope](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-reference.html).

## Vertex AI

Use customer-approved project/location, supported model/API, and workload identity or another explicitly supported customer-managed credential method. Avoid requiring downloadable service-account keys where federation is supported.

Usage metadata may contain prompt, candidates, cached-content, thought, and total counts. Cached tokens may already be included in prompt totals; adapter rules must follow the exact API/model response semantics. See [usage metadata](https://cloud.google.com/dotnet/docs/reference/Google.Cloud.AIPlatform.V1/latest/Google.Cloud.AIPlatform.V1.GenerateContentResponse.Types.UsageMetadata) and [workload federation](https://docs.cloud.google.com/iam/docs/use-workload-identity-federation-to-let-customers-access-their-cloud-resources).

## Proposed adapter contract

Declare supported capabilities, credentials, resource scope, API/model versions, collection granularity, and limits. Expose validation, collection with cursor/window, normalization, and health results. Handle pagination, bounded retries/backoff, rate limits, late events, cancellation, and credential rotation. Persist cursors only after durable observation handling.

Provider errors must remain actionable and sanitized. Unsupported fields remain absent/unknown, not fabricated zero. Keep provider payloads limited to usage metadata; prompts and completions are not collected by default. See [accounting](token-accounting.md).
