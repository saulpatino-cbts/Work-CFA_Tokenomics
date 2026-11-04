# Acceptance and test strategy

**Status:** planned tests, not executed product evidence. Repository documentation checks are separate from application, provider, deployment, or security acceptance.

## Requirement traceability

| Requirement | Acceptance evidence required |
| --- | --- |
| REQ-001/009 | Fresh customer-run install with no vendor credentials/control plane, preflight failures, resumability, upgrade and recovery. |
| REQ-002 | Secret redaction, local credential custody, rotation, scope and revocation tests. |
| REQ-003 | Admin/user/reader allowed and denied API/worker/resource operations. |
| REQ-004/005 | Vendor denied by default; scope/identity/expiry/revocation/stream/import cases. |
| REQ-006 | Independent Foundry, Bedrock, Vertex adapter contract and customer-authorized integration tests. |
| REQ-007 | API-specific normalization, unknown values, retries, overlapping windows, revisions, and reconciliation. |
| REQ-008 | Real setup checks, resumability, understandable errors, keyboard/screen-reader flow. |
| REQ-010 | Consistent full export and fresh restore, validation, identity safety, interrupted/repeated imports. |
| REQ-011 | Customer policy controls, accurate deletion scope, restore suppression, no vendor policy enforcement. |
| REQ-012 | No accidental payment/subscription/vendor billing dependencies. |

## Test layers

- Unit tests for normalization, policy evaluation, schema checks, and state transitions.
- Adapter contract tests against reviewed, sanitized usage-only provider fixtures.
- Integration tests in explicitly authorized customer/test environments.
- End-to-end setup, roles, collection, Assessment, portability, and upgrade flows.
- Security tests for direct API bypass, secret exposure, hostile imports, arbitrary endpoints, and privilege escalation.
- Recovery/failure tests for outages, duplicated jobs, throttling, expired credentials, and interrupted writes.

Synthetic fixtures may exercise behavior but must be visibly labeled test-only and must never be presented as measured provider usage or actual customer cost. Do not use real customer exports as fixtures.

## Mandatory adversarial cases

Attempt to access another workspace; write as reader; approve Assessment as vendor; use an expired/revoked grant; keep reading through an existing stream; reactivate support through import; reveal a credential through an error; submit hostile archive paths; inflate totals with overlap/replay; remove target administrators through imported roles; and run an old worker after migration cutover.

Test that missing usage stays unknown, cache categories are not blindly added, aggregate observations do not gain invented request IDs, and charge estimates are not labeled actual bills.

## Evidence contract

Each PR states exact commands, results, evidence level, and checks not run. Local lint is not CI success; mocked adapter tests are not live provider validation; an install plan is not a deployed environment. Product milestones remain unverified until the relevant tests exist and pass.

## Documentation checks

Review local Markdown links/anchors, lint with the existing repository configuration, parse changed YAML, inspect diffs for secrets/placeholders, and check terminology against requirements/ADRs. Existing inherited security workflows cover their configured scope only, not product behavior.
