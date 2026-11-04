# Product requirements

## Status and authority

These requirements capture the product owner's clarified scope. They supersede earlier vendor-operated service, iOS form-processing, appointment, commercial workflow, and vendor-controlled deletion assumptions. Implementation status is tracked in the [roadmap](roadmap.md), not implied by this document.

## Confirmed baseline

| ID | Requirement | Acceptance intent |
| --- | --- | --- |
| REQ-001 | Customer-hosted deployment only | Normal operation runs in the customer's environment without a mandatory vendor data/control plane. |
| REQ-002 | Customer-controlled credentials | Customer provisions and controls OIDC/API credentials; vendor never receives customer secret values. |
| REQ-003 | Customer admin/user/reader roles | Permissions enforced on the server and scoped to authorized resources. |
| REQ-004 | No standing vendor access | Vendor admin/support cannot read customer data by default. |
| REQ-005 | Explicit Assessment authorization | Customer-approved scope, identity, duration, revocation, and audit trail govern access. |
| REQ-006 | Three AI provider integrations | Foundry, Bedrock, and Vertex AI can be connected independently. |
| REQ-007 | Model-token accounting | Provider-specific counts, provenance, coverage, and quality are preserved without double-counting. |
| REQ-008 | Guided verified setup | Clear language, resumable steps, separate credential/model/telemetry checks, actionable errors. |
| REQ-009 | Easy repeatable deployment | Documented prerequisites, repeatable installation, health checks, upgrades, and recovery. |
| REQ-010 | Full export/import | Customer-owned state can be migrated with documented secret handling and safe validation. |
| REQ-011 | Customer-owned data lifecycle | Customer controls retention, deletion, exports, backups, and recovery policy. |
| REQ-012 | No commercial operations | Payment processing, subscriptions, refunds, and vendor billing workflows are outside scope. |

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
