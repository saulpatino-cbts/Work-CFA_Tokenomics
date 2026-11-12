# 0013. Admin-only product: org-level and per-user cost are both core

- **Status:** Accepted (owner's instruction of 2026-11-12: the product is for administrators only, tied to Entra ID first and Google Workspace second, with an admin and a finance-viewer tier; per-user cost is necessary alongside org-level cost). Pseudonymization was decided on 2026-11-12: pseudonyms by default, with an administrator option to show real names. Retention is still open.
- **Date:** 2026-11-12
- **Decision authority:** Owner
- **Owners:** Security and privacy; access control; connectors
- **Supersedes:** the privacy default in [ADR 0012](0012-privacy-modes-for-vendor-sources.md) (aggregate by default, per-user as a recorded opt-in). The rest of 0012 stands: keyed pseudonyms, fixed hosts, read-only credentials, content-bearing sources never connected.
- **Issue:** None exists
- **Implementation evidence:** the two-role model (`authz.py`, migration 0010) and the people mapping with the display setting (`people.py`, migration 0011, `tests/test_people.py`). Per-user connector mode and the Entra ID and Google directory sync are **not built**; names enter today only through `people-import` (manual).

## Context

The product's purpose is to give administrators the cost and the value or return of Gen AI and agentic AI, for the organization and for each person. ADR 0012 treated person-level data as an opt-in risk. That does not fit the purpose: per-user cost is a core view, and the control that makes it acceptable is that only administrators can see anything.

## Decision

1. **Administrators only.** There is no end-user role. Two roles exist: `admin` (everything) and `finance_viewer` (read-only: the cost, usage and economics views; no writes, no connector or identity management). Existing `user` and `reader` assignments become `finance_viewer` (migration 0010), so nobody gains access.
2. **Org-level and per-user views are both always available** to those roles. Per-user mode is no longer an opt-in setting; it is how the connectors run, wherever the source provides person-level data. Content-bearing sources stay unconnected in every case.
3. **Sign-in is the customer's directory:** Entra ID first, then Google Workspace, through OIDC group claims mapped to the two roles (`CFA_OIDC_ADMIN_GROUP`, `CFA_OIDC_FINANCE_GROUP`). The first-admin bootstrap remains break-glass only.
4. **Per-user cost is built in layers and labelled.** Direct AI spend (tokens, seats) is attributed to a person from vendor usage. Shared platform and cloud cost, which has no user dimension, is allocated by usage share through the existing allocation engine. Every figure keeps its observed, estimated or assumed label and its Explain trail. Vendor accounts that cannot be matched to a person stay visible as *unattributed*; nothing is dropped.
5. **Identity resolution** maps each vendor identifier (OpenAI user, Anthropic actor, cloud principal) to one canonical person taken from the directory, with administrator overrides for mismatches.
6. **Scope.** Account grants (ADR 0008) already restrict a non-admin to listed accounts. Scoping a finance viewer further (for example by business unit) is intended and comes with the person model; admins are unrestricted.

## Names or pseudonyms: decided

Stored usage and cost rows hold only keyed pseudonyms, always. A separate `people` table maps a pseudonym to a display name (a name and nothing else: no email, no directory id). A tenant setting `person_display` is `pseudonym` (the default) or `name`; an administrator switches it (`PUT /v1/admin/people/display`, or `person-display` in the operator CLI). In `name` mode the product shows the name for every pseudonym it can resolve and keeps showing the pseudonym, as unattributed, for any it cannot. Switching back hides names again at once. Showing names never copies a name into cost or usage data. Every switch is audited, and every lookup of names is audited as a count, never as the names.

## Open (owner to decide)

- **Retention** for person-level rows (ADR 0012 proposed 90 days; the customer sets it).

## Consequences

- The Anthropic and Codex connectors need a per-user path (storage, pseudonyms, identity resolution) before the per-user views exist. They still refuse per-user rows today.
- API and screens must require an administrative role; negative tests exist for the finance viewer and there is no other role.
- Raw FOCUS copies still keep the 1.5 identity columns (R-17); with an admin-only product this is a smaller exposure but remains an open choice.
