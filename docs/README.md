# Documentation index

This is the source-controlled documentation for Work-CFA_Tokenomics. It describes the agreed customer-hosted product and proposed implementation contracts. No product runtime is implemented yet.

## Reading order

1. [Requirements](requirements.md): confirmed scope, non-goals, and traceable requirement IDs.
2. [Architecture](architecture.md): logical components, data flows, and unresolved hosting choices.
3. [Roles and identity](access-control.md): customer roles, credentials, and authorization.
4. [Assessment](assessment.md): customer-approved vendor access and revocation.
5. [Providers](providers.md) and [token accounting](token-accounting.md): integration capabilities and measurement semantics.
6. [Marketplace distribution](marketplace.md), [Deployment](deployment.md) and [onboarding](onboarding.md): installation prerequisites and guided verification.
7. [Portability](portability.md) and [data ownership](data-ownership.md): full migrations and customer policy.
8. [Operations](operations.md) and [testing](testing.md): day-two procedures and release evidence.
9. [UI concepts](ui-concepts.md), [Roadmap](roadmap.md), [risks](risk-register.md), and [ADRs](adr/README.md): delivery order, decisions, and blockers.

## Documentation conventions

- **Confirmed requirement:** explicitly requested product behavior, identified by REQ IDs.
- **Accepted decision:** a product boundary recorded in an accepted ADR; not evidence that it is implemented.
- **Proposed contract:** a recommended interface or operating behavior awaiting implementation review.
- **Open decision:** unresolved design choice; do not silently convert it into a requirement.
- **Implemented/verified:** use only with a source change and recorded test evidence.

Every implementation PR must link affected requirement IDs, describe security/data implications, and report actual checks run. Update documentation with behavior changes, not afterward.

## Repository administration

[Maintainer setup](TEMPLATE.md) replaces the inherited template checklist. [Legacy README input](README.project.md) is retained only because inherited initialization scripts reference it; it is not an installer or authoritative product README. [Authoring templates](../.github/templates/README.md) remain reusable writing aids.

Product documentation is maintained here rather than in a separate wiki so changes can be reviewed with implementation. A future wiki may link here but must not become a conflicting source of truth.
