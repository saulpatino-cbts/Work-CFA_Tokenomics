# Architecture decision records

ADRs capture product boundaries and implementation choices. **Accepted** means the decision is approved, not that code exists. This initial set records explicit owner requirements; unresolved technical choices remain open.

## Decision index

| Record | Status | Decision |
| --- | --- | --- |
| [0001](0001-customer-hosted-boundary.md) | Accepted requirement | Customer-hosted runtime, customer credential/data ownership, no commercial operations. |
| [0002](0002-roles-and-assessment.md) | Accepted requirement | Customer admin/user/reader roles and no standing vendor data access. |
| [0003](0003-portability-and-provider-scope.md) | Accepted requirement | Three-provider token accounting and validated full portability. |

## Open technical decisions

Runtime/frontend/backend stack; initial hosting target; persistence; observation mode and grain; Assessment transport; archive format and secret migration; compatible API/model versions; cost-data scope; and licensing. Propose records for these before implementing the affected boundary.

## Workflow

Copy [template](template.md), use the next sequential number, link relevant requirement IDs and available issue, and state alternatives, consequences, validation, and revisit conditions. Do not invent an issue number or claim acceptance without owner authority.

When a decision changes, create a superseding record and mark the earlier record superseded rather than silently rewriting its rationale. Source-controlled ADRs are canonical; a wiki may link to them.
