# 0008. Account-scoped usage access

- **Status:** Proposed (implemented on the owner's go-ahead to proceed; scope model awaits explicit confirmation)
- **Date:** 2026-11-06
- **Decision authority:** Product owner
- **Owners:** Identity
- **Requirements:** REQ-003
- **Issue:** No issue exists
- **Implementation evidence:** `account_grants` table (migration `0003`), grant routes, scoped `GET /v1/usage`, and 10 tests against PostgreSQL.

## Context

[Access control](../access-control.md) says users and readers see only assigned scope and that final resource scopes need approval. Before this change any usage-read role saw every account in the ledger.

## Decision

Propose the smallest scope model that closes that gap:

- The scope unit is a **(provider, account)** pair, matching the ledger.
- **Admins** are unrestricted. **Users and readers** see only accounts explicitly granted to their identity (issuer + subject). No grant means no data (deny by default).
- Admins manage grants with `PUT/DELETE /v1/admin/grants`; every change writes an audit event.
- The scope applies to rows and to collection freshness. Asking for an account outside the grant returns an empty result, not an error that confirms the account exists.
- Grants are per identity, not per IdP group, and there is no workspace concept yet.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Group-based grants | Fewer rows to manage | Needs claim-to-scope mapping design and approval | Deferred; can layer on later |
| Workspaces first | Matches the proposed "workspace" wording | Larger model, not yet defined | Deferred until the owner defines workspaces |

## Consequences

Customers must grant accounts before non-admins see data. Roles are unchanged. Assessment grants (vendor access) are not implemented and must use this same scope check when added. Import/export must carry grants without reactivating support access.

## Validation

Tests cover no grants, a grant, per-identity isolation, revoke, non-admin denial, audit, idempotence, and migration downgrade. Untested: group-based scoping, workspaces, large grant sets.

## Rollback or revisit trigger

Reopen if the owner defines workspaces or requires group-based scoping.
