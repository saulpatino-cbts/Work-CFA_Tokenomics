# 0007. Observation mode and reconciliation

- **Status:** Accepted (owner decision 2026-11-06: both sources, reconciled); implementation started
- **Date:** 2026-11-06
- **Decision authority:** Product owner
- **Owners:** FinOps, Connectors
- **Requirements:** REQ-006, REQ-007
- **Issue:** No issue exists
- **Implementation evidence:** Ledger tables, migration `0002`, reconciliation rules and a Bedrock metric normalizer with tests. No live provider call exists; fixtures are synthetic.

## Context

Risk R-03 (observation coverage) and [token accounting](../token-accounting.md). Application-routed requests give per-request detail but miss other callers. Provider telemetry sees more traffic but only as delayed aggregates. Adding the two would double-count.

## Decision

Collect both and keep them in **separate stores**, never merged by addition:

- **Request observations:** one row per model-call attempt routed through the app. Identity is `provider|account|request_id|attempt`; replays are idempotent.
- **Aggregate observations:** provider metric windows. Identity is provider, scope, model, category, window, statistic. A revised value replaces the old one and increments a revision.
- **Reconciliation** is computed per (provider, scope, model, window, category) and never sums the two sources:
  - Only requests: `app_only` (covers routed traffic only).
  - Only aggregate: `provider_only` (no per-request detail).
  - Both, app <= provider: total is the provider value; the difference is shown as `unattributed` (traffic the app did not route).
  - Both, app > provider: `app_exceeds_provider` (provider lag or a window mismatch); total is the app value and the row is flagged.
  - Any missing category value stays unknown, never zero; partially known sums are flagged `partial`.
- Token categories are kept as the provider defines them. No generic sum of categories is computed.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Telemetry only | Simple, covers bypass traffic | No per-request or per-user detail | Owner chose both |
| Proxy only | Per-request tokens | Misses direct calls | Owner chose both |

## Consequences

More storage and rules than either alone. Per-user attribution exists only for request observations with authenticated correlation. Billing and cost are out of scope here (no price tables).

## Validation

Unit tests for each reconciliation case, replay idempotence, aggregate revision, and unknown-not-zero. Integration tests against real providers are not done.

## Rollback or revisit trigger

Reopen if a provider revises windows in a way the replacement rule cannot represent, or if customers cannot supply telemetry access.
