# Product requirements

## Status and authority

These requirements capture the product owner's clarified scope. They supersede earlier vendor-operated service, iOS form-processing, appointment, commercial workflow, and vendor-controlled deletion assumptions. Implementation status is tracked in the [roadmap](roadmap.md), not implied by this document.

## Confirmed baseline

| ID | Requirement | Acceptance intent |
| --- | --- | --- |
| REQ-001 | Customer-hosted deployment only | Normal operation runs in the customer's environment without a mandatory vendor data/control plane. |
| REQ-002 | Customer-controlled credentials | Customer provisions and controls OIDC/API credentials; vendor never receives customer secret values. |
| REQ-003 | Customer admin and finance-viewer roles (admin-only product, ADR 0013) | Permissions enforced on the server and scoped to authorized resources. |
| REQ-004 | No standing vendor access | Vendor admin/support cannot read customer data by default. |
| REQ-005 | Explicit Assessment authorization | Customer-approved scope, identity, duration, revocation, and audit trail govern access. |
| REQ-006 | Three AI provider integrations | Foundry, Bedrock, and Vertex AI can be connected independently. |
| REQ-007 | Model-token accounting | Provider-specific counts, provenance, coverage, and quality are preserved without double-counting. |
| REQ-008 | Guided verified setup | Clear language, resumable steps, separate credential/model/telemetry checks, actionable errors. |
| REQ-009 | Easy repeatable deployment | Documented prerequisites, repeatable installation, health checks, upgrades, and recovery. |
| REQ-010 | Full export/import | Customer-owned state can be migrated with documented secret handling and safe validation. |
| REQ-011 | Customer-owned data lifecycle | Customer controls retention, deletion, exports, backups, and recovery policy. |
| REQ-012 | No commercial operations | Payment processing, subscriptions, refunds, and vendor billing workflows are outside scope. |

## Owner-stated scope, 2026-11-07 (pending ADR 0011)

The owner's brief reframes the product as an application-centric AI economics platform. These are **proposed requirements** until [ADR 0011](adr/0011-ai-economics-platform.md) is accepted. Design: [economics set](economics/README.md).

| ID | Requirement | Acceptance intent |
| --- | --- | --- |
| REQ-013 | Application-centric economics | Cost, value, unit economics, price and margin are computed per application and filterable by customer, environment, provider, model, team, workload, scenario and period. |
| REQ-014 | FOCUS-aligned cost model | Cloud, AI, SaaS and internal costs share a FOCUS-compatible normalized model; FinOps Foundation concepts are used rather than a proprietary method. |
| REQ-015 | Observed, estimated and assumed | Every figure carries its basis; an estimate is never presented as telemetry. |
| REQ-016 | Business value model | Editable, visible assumptions produce hours saved, labour value, net value, ROI and payback. |
| REQ-017 | Scenarios and sensitivity | Baseline, Current, Forecast, Optimized and Customer Proposal scenarios recalculate cost, value, ROI, price and margin; sensitivity on key drivers. |
| REQ-018 | Commercial and marketplace modelling | Price models, required price for a target margin, and configurable marketplace fees and commitment effects. **Modelling only** (see REQ-012 note). |
| REQ-019 | Provenance | Any important number traces to calculation, input, source and timestamp. |
| REQ-020 | Connector framework | New sources are added without redesign; no source is assumed to expose tokens; manual import is supported. |
| REQ-021 | Enterprise security | Tenant isolation, RBAC, SSO, secret management, audit, connector health, retention, ingestion traceability; no credential in client code. |
| REQ-022 | Executive experience | Economics-first dashboards answering the ten executive questions; tokens are drill-down. |

**Proposed clarification of REQ-012:** modelling prices, margins and marketplace economics is in scope; payment processing, invoicing customers, subscription billing operations and marketplace metering remain out of scope.

## Intended outcomes

Customer administrators can deploy and configure the platform without sharing credentials with the vendor. Authorized users can inspect permitted usage, understand data freshness and coverage, and request an Assessment without opening permanent support access. Administrators can export and restore customer-owned state and apply their own data policies.

The product tracks cloud/AI usage for FinOps. Estimated spend, actual provider charges, and model tokens are different measures. Collection of billing data, pricing sources, forecasting, anomaly detection, and PR cost projections need explicit feature decisions before implementation; the product description alone does not establish those capabilities.

## Proposed quality requirements

- Deny unauthorized actions on API, worker, import, export, and support paths.
- Keep secret values and prompt/completion bodies out of ordinary telemetry and archives.
- Show stale, partial, unavailable, estimated, and verified states distinctly.
- Make retries and repeated collection/import operations safe.
- Make upgrades and migrations reversible or provide a documented recovery route.
- Test setup and core tasks for keyboard navigation, screen-reader use, and understandable errors.

Quantitative performance, capacity, recovery-time, data-loss, and support targets remain open. Do not publish invented service levels.

## Open decisions

Hosting targets and runtime stack; first implementation language/framework; provider observation mode; Assessment transport; secret migration policy; storage and archive formats; supported model/API versions; cost-data scope; and licensing. See [risks](risk-register.md) and [decisions](adr/README.md).
