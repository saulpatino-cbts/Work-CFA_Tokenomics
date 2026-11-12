# Roles and identity

**Status:** two roles (admin, finance viewer) with a proposed least-privilege permission matrix. Final object/resource scopes must be approved before implementation.

## Separate identity flows

| Identity | Purpose | Boundary |
| --- | --- | --- |
| Human OIDC identity | Customer sign-in | Validate issuer, audience, signature, expiry, and configured claims; authorize on the server. |
| Workload identity | Provider/API/telemetry access | Customer-controlled, scoped, preferably short-lived credentials. |
| Application API key | Customer automation when needed | Scoped service principal equivalent, hashed/securely stored, revocable, expiring under customer policy. |
| Vendor support identity | Approved Assessment | Named external identity with no authority outside an active customer grant. |

OIDC sign-in does not itself grant cloud-provider permissions. An inference API key does not establish monitoring or billing access. Never reuse a shared provider key as a human administration credential.

## Roles

The product is for administrators only ([ADR 0013](adr/0013-admin-only-product-and-per-user-cost.md)). There is no end-user role. Sign-in is the customer's directory (Entra ID first, then Google Workspace) through OIDC group claims.

| Capability | Admin | Finance viewer | Vendor admin/support |
| --- | --- | --- | --- |
| Identity and role mapping | Manage | No | No standing access |
| Provider and connector management | Manage/test | No | Approved Assessment metadata only |
| Cost, usage and economics views (org and per user) | All | Read; limited by account grants | Active Assessment scope only |
| Economics writes (applications, assumptions, allocation, scenarios) | Yes | No | No |
| Full export/import | Yes, explicit confirmation | No | No |
| Retention/deletion policy | Customer controls | No | No |
| Grant/revoke Assessment | Yes | No | Cannot self-approve |
| Reveal stored secret values | No retrieval by default | No | Never |

`CFA_OIDC_ADMIN_GROUP` maps to Admin and `CFA_OIDC_FINANCE_GROUP` to Finance viewer. Earlier `user` and `reader` assignments became finance viewers (migration 0010); the `CFA_OIDC_USER_GROUP` and `CFA_OIDC_READER_GROUP` settings no longer exist.

Admins configure secrets through protected write-only flows or local secret references. Customer cloud administrators may have separate infrastructure privileges; application roles must not pretend to restrict those independent privileges.

## Required enforcement

Deny by default; evaluate permissions on each action, object, and resource scope. Enforce the same checks in API handlers, workers, search, downloads, import/export, and support sessions. Hiding a button is not authorization. Include negative tests for every role.

Map OIDC subjects using issuer and subject, not email alone. Establish a customer-controlled first-admin bootstrap, validate group/claim mapping, prevent accidental removal of the last usable administration path, and document identity-provider outage recovery. Recovery must not introduce vendor master credentials.

Automation keys need identifiers, scopes, creation/expiry metadata, rotation, revocation, and audit attribution. Do not log bearer values. Support identities must never obtain arbitrary database, shell, cloud-console, or execution access as an implicit side effect of read-only Assessment.

## Credentials and migration

Only customer-local runtime components may use customer-authorized credentials. The vendor must not receive copies through logs, archives, support tools, CI outputs, or infrastructure state. An approved secret-migration design must address encryption/key custody and fresh authorization; the default portability proposal excludes live secrets.

Authorization behavior must be validated against [acceptance tests](testing.md) and [Assessment rules](assessment.md).
