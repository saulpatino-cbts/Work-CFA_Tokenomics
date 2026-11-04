# Customer-approved Assessment

**Status:** confirmed opt-in access requirement with a proposed grant lifecycle. Assessment transport remains an open architecture decision.

## Default state

Vendor admins/support have no customer-data access. The Assessment button initiates review and authorization; it must not create a permanent vendor role, share customer credentials, or silently upload diagnostics.

## Proposed grant lifecycle

1. A customer admin chooses the purpose, resource scope, data categories, named assessor, and duration.
2. The UI previews exactly what may be viewed and whether anything will leave the environment.
3. Customer confirms; the installation creates and audits a scoped grant.
4. The named support identity authenticates through the approved route and receives only granted read access.
5. A visible banner shows active access, expiry, and **Revoke now**.
6. Customer revocation or expiry blocks subsequent access, including workers, streams, cached decisions, and long-lived sessions within the documented enforcement bound.
7. Closure records permitted access activity and grant outcome without retaining sensitive payloads.

A proposed grant contains installation/resource scope, approver subject/issuer, assessor identity, purpose, permission set, data categories, issued/expiry timestamps, state, and revocation evidence. Timestamps are UTC. Imported historical grants are evidence, never active authority.

## Access modes awaiting selection

| Mode | Benefit | Constraint |
| --- | --- | --- |
| Live customer-local read-only access | Current view without transferring a diagnostic dataset | Needs an approved identity and network route into a private installation. |
| Customer-generated bundle | Supports environments without inbound support access | Data leaves the environment if transferred; preview, minimization, encryption, custody, and explicit consent are mandatory. |
| Customer-presented session | Customer remains present | Screen sharing still discloses information; limit visible content and use an approved channel. |

No production transport is selected. Choose and test one initial mode before presenting Assessment as operational. Optional vendor-side coordination must not become a mandatory control plane or grant customer-data access by itself.

## Non-negotiable restrictions

Assessment does not grant secret values, role administration, full export/import, deletion, arbitrary code execution, provider invocation, or infrastructure credentials. Default metadata visibility excludes prompts, completions, raw documents, and unrestricted logs. Additional data categories require explicit customer authorization.

Revocation cannot retract information already viewed or deliberately transferred. Do not imply otherwise. Customer-local read-only access must be enforced through the supported access path, not merely a UI label over a broadly privileged identity.

## Required tests

Attempt access before approval, after expiry, after revocation, as a different assessor, outside scope, through direct APIs, through an active stream, and after restoring/importing grant history. Verify that exporting a dataset or invoking a model remains denied.
