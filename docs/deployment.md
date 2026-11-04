# Deployment contract

**Status:** requirements and proposed installation lifecycle, not executable instructions. No deployment package or supported hosting profile exists yet.

## Hosting is a separate choice

Foundry, Bedrock, and Vertex AI are required integration targets. That does not mean the application is already deployable natively on Azure, AWS, and Google Cloud. Select and document the first supported runtime, target cloud/platform, persistence, network profile, sizing, and compatibility matrix through an ADR.

## Customer-run preflight

Before a browser wizard can run, a customer operator must verify:

- Deployment identity and narrowly scoped permissions.
- Runtime capacity, quotas, image/package access, and supported versions.
- DNS, TLS, ingress, egress, proxy, and private endpoint requirements.
- Customer identity-provider application and callback configuration.
- Database/object storage/secret-store readiness and backup choices.
- Customer-controlled infrastructure state/locking, when IaC is selected.
- Approved provider endpoints and optional private Assessment connectivity.

Do not ask for credentials in a public issue or use vendor credentials to bootstrap customer resources. Preflight must explain missing prerequisites before a partially successful install hides them.

## Proposed installation lifecycle

1. Fetch a versioned artifact and verify provenance/checksum using the documented release process.
2. Review permissions, external destinations, expected resources, and cost-bearing actions.
3. Run a read-only preflight and preview changes.
4. Provision/install with customer authority and durable retry-safe state.
5. Configure storage, local observability, identity, and first-admin recovery.
6. Run health checks before exposing the setup wizard.
7. Complete [guided onboarding](onboarding.md).
8. Record installed version and validation evidence inside the customer environment.

Failures must identify what was created, what remains, and how to resume or remove it. No destructive cleanup by default. No installer may send secrets, plans, telemetry, or customer data to the vendor implicitly.

## Upgrades and removal

Version application, schema, archive format, provider adapters, and deployment contract separately where needed. Preview migrations, take customer-approved recovery checkpoints, test supported version transitions, and document rollback limitations for stateful changes.

Uninstall must distinguish runtime removal from deleting customer data. Default behavior must not silently destroy retained databases, archives, backups, or secret stores. A customer-authorized destructive option needs explicit scope and warnings.

## IaC and automation

Terraform or another IaC tool must be selected before claiming support. If Terraform is used, its backend, encryption, locking, permissions, and plans remain customer-controlled; marking a value sensitive does not automatically exclude it from state. See [HashiCorp sensitive data guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

Inherited `scripts/Initialize-Repo.ps1`, `scripts/initialize-repo.sh`, and `overlays/` are repository-template utilities, not platform installers. Do not run them against this customized project. Toolchain and CI cloud authentication choices remain separate from customer runtime authentication.
