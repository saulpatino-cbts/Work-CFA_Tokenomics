# 0002. Roles and customer-approved Assessment

- **Status:** Accepted requirement; detailed enforcement/transport pending.
- **Date:** 2026-11-03
- **Decision authority:** Repository owner product clarification.
- **Requirements:** REQ-003, REQ-004, REQ-005.

## Context

The vendor has administrators/support. Each customer has administrators, users, and readers. Vendor support must not automatically gain customer-data access.

## Decision

Maintain separate vendor and customer authority domains. Customer roles govern installation/workspace resources. Vendor identities have no standing customer-data access; an explicit customer-authorized Assessment controls any support view.

The detailed permission matrix and grant lifecycle are proposed in [roles](../access-control.md) and [Assessment](../assessment.md). Time bounds, least privilege, revocation, and auditability are design controls needed to make the opt-in boundary enforceable; exact transport and operational duration remain open.

## Alternatives considered

Permanent vendor superadministrator access, shared customer credentials, or an unscoped support flag would contradict the customer's stated approval boundary and are rejected.

## Consequences

Authentication is insufficient without resource authorization. Support must not bypass the grant through database/cloud/shell access. The product needs a usable customer approval/revocation flow and an approved network route for private environments.

## Validation

Test no-default access, explicit approval, assessor identity, scope, expiry/revocation, active streams, and imported/restored historical grants. No runtime evidence exists yet.

## Revisit trigger

Any proposed support write/remediation capability or diagnostic data transfer requires a distinct reviewed permission and updated threat analysis, not a quiet extension of read-only Assessment.
