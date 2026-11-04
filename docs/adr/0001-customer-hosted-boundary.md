# 0001. Customer-hosted ownership boundary

- **Status:** Accepted requirement; implementation pending.
- **Date:** 2026-11-03
- **Decision authority:** Repository owner product clarification.
- **Requirements:** REQ-001, REQ-002, REQ-009, REQ-011, REQ-012.

## Context

Earlier discussion assumed a vendor-operated client service. The owner clarified that this product is turnkey software deployed only in customer environments with customer-controlled credentials and customer-owned data/deletion.

## Decision

The customer hosts the application and controls runtime data, credentials, operations policy, and installation authority. Normal operation must not require a vendor data/control plane or vendor-held customer secrets. Exclude commercial operations and vendor-enforced retention/deletion workflows.

## Alternatives considered

A vendor-hosted SaaS or shared credential broker would simplify centralized operations but conflicts with the confirmed custody boundary. Mandatory vendor analytics would also conflict with the no-default-data-sharing requirement.

## Consequences

Install/upgrade/recovery and customer-local observability are product responsibilities. Customer policy control does not excuse missing export/delete/backup mechanisms. External provider processing remains an explicit configured flow. Runtime technology and initial hosting platform are not selected by this ADR.

## Validation

Demonstrate a fresh install and normal operation without vendor credentials or mandatory vendor endpoints. Verify customer-controlled state, secrets, logging, and data-policy controls. No such implementation evidence exists yet.

## Revisit trigger

Only an explicit owner-approved scope change can introduce a vendor service dependency, broader processing boundary, or commercial operations. Record it as a superseding ADR.
