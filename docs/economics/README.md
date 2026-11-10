# AI economics platform: redesign

**Status:** proposed, written 2026-11-07 from the owner's brief. This set treats the existing token application as a **prototype, not the specification**. It starts with the assessment and target architecture; no major implementation change has been made.

## The outcome

The platform should let an organization say: *"This AI application consumed X resources, cost Y dollars to operate, produced Z dollars of measurable business value, has an effective unit cost of A, and can be commercially offered at B while achieving C margin."* Token consumption is one input, not the product.

```text
AI usage -> tokens -> infrastructure -> cloud cost -> application cost -> business value -> unit economics -> pricing -> margin -> marketplace economics
```

## Contents

| Part | Document | Brief section |
| --- | --- | --- |
| A, B | [Current state and gap analysis](01-current-state-and-gap-analysis.md) (KEEP, REFACTOR, REMOVE, BUILD) | 12, 13A, 13B |
| C | [Target architecture](02-target-architecture.md) | 8, 9, 13C |
| D | [Canonical data model](03-data-model.md) (FOCUS 1.4 alignment) | 2, 3, 4, 10, 13D |
| E | [Connector framework](04-connectors.md) (sourced capability matrix) | 2, 13E |
| F | [Calculation engine](05-calculation-engine.md) (cost, value, ROI, scenarios, pricing, margin) | 5, 6, 7, 13F |
| G | [UX and dashboard redesign](06-ux.md) | 11, 13G |
| H | [Delivery roadmap](07-roadmap.md) (four phases with acceptance criteria) | 13H |
| - | [FOCUS 1.5 readiness](08-focus-1-5-readiness.md) (December 2026 release preparation) | 4 |
| - | [Vendor API research](09-vendor-api-research.md) (Phase 2 preparation, documentation-sourced, nothing run) | 4 |

Decision record: [ADR 0011](../adr/0011-ai-economics-platform.md). New requirements: [REQ-013 to REQ-022](../requirements.md#owner-stated-scope-2026-11-07-pending-adr-0011).

## What the research established

Three documentation reviews (FOCUS and the FinOps Foundation; Azure and AWS cost and AI telemetry; AI vendor usage APIs) shaped the design. Highlights, each sourced in the linked documents:

- **FOCUS 1.4 is current; 1.5 is due for ratification in December 2026** and recommends token conventions (`Token` unit, `TokenDirection`, `TokenCacheAction`, model identity properties). FOCUS 1.4 itself has no AI-specific columns.
- **Sources disagree on FOCUS version** (Azure exports 1.2-preview; AWS offers 1.0 and 1.2), so the cost layer upgrades inputs to one version.
- **Cost authority is billing data.** Bedrock and Azure OpenAI token metrics explain and allocate cost; they do not replace the bill. Azure's own `FoundryModelEstimatedCost` is documented as an estimate, not an invoice.
- **Microsoft 365 Copilot exposes activity and prompt counts, not tokens or cost.** GitHub Copilot exposes seats, premium-request and billing amounts, and only partial token data. Claude Code analytics do not include subscription-plan usage.
- **Several sources return per-user data and Bedrock invocation logs contain prompt bodies**, so privacy-by-default ingestion is a requirement.
- **Data is revised after publication** (Azure until about five days after period end; Anthropic until about a week after month end), so every fact carries `provisional` or `final`.
- Several details were **not found** in the documentation read (for example Cost Explorer limits, Data Exports latency, Codex usage fields, Vertex AI billing export). They are listed as open verification items, not assumed.

## Decisions needed

These are the owner's to make; recommendations are mine.

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | **Tenancy.** The brief asks for tenant isolation; ADR 0001 says customer-hosted. | Keep customer-hosted. Enforce `tenant_id` and row-level security from the start so multi-tenant or managed-service operation later is not a rewrite. Decide separately whether CBTS will operate it for several clients. |
| 2 | **REQ-012** excludes "commercial operations". The brief adds pricing, margin and marketplace modelling. | Clarify: *modelling* prices, margins and marketplace economics is in scope; payment processing, invoicing customers, subscription billing operations and marketplace metering remain out. |
| 3 | **"Customer"** in the model means a buyer of an application the organization sells. | Confirm. It is distinct from the tenant (the deploying organization). |
| 4 | **First real data for Phase 1 acceptance.** | Name one FOCUS export (Azure or AWS) and one AI usage file or API to use. |
| 5 | **FOCUS target.** | 1.4 now; adopt the 1.5 token conventions once ratified. |
| 6 | **Value defaults.** Should realization and cashability factors have defaults? | No defaults; require an explicit entry with a rationale, shown with its basis. |
| 7 | **Currency.** | One base currency per tenant; dated FX rates for conversion. |
| 8 | **Per-user data.** | Aggregate by default; pseudonymize when needed; privacy review before any per-user source (R-17). |
| 9 | **Agent instructions.** `AGENTS.md` lists Foundry, Bedrock and Vertex AI as the required integrations. | Update after ADR 0011 is accepted. Not changed in this proposal. |

## What happens next

On approval of ADR 0011, Phase 1 begins ([roadmap](07-roadmap.md)). Until then the existing token application keeps working and receives no new token-only features.
