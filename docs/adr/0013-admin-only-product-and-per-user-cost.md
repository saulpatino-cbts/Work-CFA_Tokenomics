# 0013. Admin-only product: org-level and per-user cost are both core

- **Status:** Accepted (owner's instruction of 2026-11-12: the product is for administrators only, tied to Entra ID first and Google Workspace second, with an admin and a finance-viewer tier; per-user cost is necessary alongside org-level cost). The pseudonymization and retention points below are **proposed and open** until the owner answers them.
- **Date:** 2026-11-12
- **Decision authority:** Owner
- **Owners:** Security and privacy; access control; connectors
- **Supersedes:** the privacy default in [ADR 0012](0012-privacy-modes-for-vendor-sources.md) (aggregate by default, per-user as a recorded opt-in). The rest of 0012 stands: keyed pseudonyms, fixed hosts, read-only credentials, content-bearing sources never connected.
- **Issue:** None exists
- **Implementation evidence:** this change adds only the two-role model (`authz.py`, migration 0010). Per-user connector mode, identity resolution and the directory sync are **not built**.

## Context

The product's purpose is to give administrators the cost and the value or return of Gen AI and agentic AI, for the organization and for each person. ADR 0012 treated person-level data as an opt-in risk. That does not fit the purpose: per-user cost is a core view, and the control that makes it acceptable is that only administrators can see anything.

## Decision

1. **Administrators only.** There is no end-user role. Two roles exist: `admin` (everything) and `finance_viewer` (read-only: the cost, usage and economics views; no writes, no connector or identity management). Existing `user` and `reader` assignments become `finance_viewer` (migration 0010), so nobody gains access.
2. **Org-level and per-user views are both always available** to those roles. Per-user mode is no longer an opt-in setting; it is how the connectors run, wherever the source provides person-level data. Content-bearing sources stay unconnected in every case.
3. **Sign-in is the customer's directory:** Entra ID first, then Google Workspace, through OIDC group claims mapped to the two roles (`CFA_OIDC_ADMIN_GROUP`, `CFA_OIDC_FINANCE_GROUP`). The first-admin bootstrap remains break-glass only.
4. **Per-user cost is built in layers and labelled.** Direct AI spend (tokens, seats) is attributed to a person from vendor usage. Shared platform and cloud cost, which has no user dimension, is allocated by usage share through the existing allocation engine. Every figure keeps its observed, estimated or assumed label and its Explain trail. Vendor accounts that cannot be matched to a person stay visible as *unattributed*; nothing is dropped.
5. **Identity resolution** maps each vendor identifier (OpenAI user, Anthropic actor, cloud principal) to one canonical person taken from the directory, with administrator overrides for mismatches.
6. **Scope.** Account grants (ADR 0008) already restrict a non-admin to listed accounts. Scoping a finance viewer further (for example by business unit) is intended and comes with the person model; admins are unrestricted.

## Open (proposed, owner to decide)

- **Pseudonymize at rest, or store names?** Proposed: keep keyed pseudonyms in the stored facts, and let an administrator resolve a pseudonym to a person through the directory mapping, with every resolution written to the audit log. Storing names in the clear is simpler but widens what a database copy reveals.
- **Retention** for person-level rows (ADR 0012 proposed 90 days; the customer sets it).

## Consequences

- The Anthropic and Codex connectors need a per-user path (storage, pseudonyms, identity resolution) before the per-user views exist. They still refuse per-user rows today.
- API and screens must require an administrative role; negative tests exist for the finance viewer and there is no other role.
- Raw FOCUS copies still keep the 1.5 identity columns (R-17); with an admin-only product this is a smaller exposure but remains an open choice.
