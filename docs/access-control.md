# Roles and identity

**Status:** required role names with a proposed least-privilege permission matrix. Final object/resource scopes must be approved before implementation.

## Separate identity flows

| Identity | Purpose | Boundary |
| --- | --- | --- |
| Human OIDC identity | Customer sign-in | Validate issuer, audience, signature, expiry, and configured claims; authorize on the server. |
| Workload identity | Provider/API/telemetry access | Customer-controlled, scoped, preferably short-lived credentials. |
| Application API key | Customer automation when needed | Scoped service principal equivalent, hashed/securely stored, revocable, expiring under customer policy. |
| Vendor support identity | Approved Assessment | Named external identity with no authority outside an active customer grant. |

OIDC sign-in does not itself grant cloud-provider permissions. An inference API key does not establish monitoring or billing access. Never reuse a shared provider key as a human administration credential.

## Proposed permissions

| Capability | Customer admin | Customer user | Customer reader | Vendor admin/support |
| --- | --- | --- | --- | --- |
| Identity and role mapping | Manage | No | No | No standing access |
| Provider connections | Manage/test | Use approved scope | View permitted status | Approved Assessment metadata only |
| Records/workspaces | Manage authorized scope | Create/change assigned scope | Read assigned scope | Approved read-only scope only |
| Usage dashboards | Authorized customer scope | Assigned scope | Assigned scope | Active Assessment scope only |
| Full export/import | Yes, explicit confirmation | No by default | No by default | No |
| Retention/deletion policy | Customer controls | Explicit delegation only | No | No |
| Grant/revoke Assessment | Yes | No by default | No | Cannot self-approve |
| Reveal stored secret values | No retrieval by default | No | No | Never |

Admins configure secrets through protected write-only flows or local secret references. Customer cloud administrators may have separate infrastructure privileges; application roles must not pretend to restrict those independent privileges.

## Required enforcement

Deny by default; evaluate permissions on each action, object, and resource scope. Enforce the same checks in API handlers, workers, search, downloads, import/export, and support sessions. Hiding a button is not authorization. Include negative tests for every role.

Map OIDC subjects using issuer and subject, not email alone. Establish a customer-controlled first-admin bootstrap, validate group/claim mapping, prevent accidental removal of the last usable administration path, and document identity-provider outage recovery. Recovery must not introduce vendor master credentials.

Automation keys need identifiers, scopes, creation/expiry metadata, rotation, revocation, and audit attribution. Do not log bearer values. Support identities must never obtain arbitrary database, shell, cloud-console, or execution access as an implicit side effect of read-only Assessment.

## Credentials and migration

Only customer-local runtime components may use customer-authorized credentials. The vendor must not receive copies through logs, archives, support tools, CI outputs, or infrastructure state. An approved secret-migration design must address encryption/key custody and fresh authorization; the default portability proposal excludes live secrets.

Authorization behavior must be validated against [acceptance tests](testing.md) and [Assessment rules](assessment.md).
