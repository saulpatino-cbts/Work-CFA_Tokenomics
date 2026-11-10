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

## Database role and tenant isolation

Tenant isolation is enforced by PostgreSQL row-level security (migration `0005`). **A superuser, or a role with `BYPASSRLS`, ignores it**, so the application must not run as one, and `/readyz` returns 503 (`role_bypasses_rls`) if it does. Use the owner role only for migrations.

1. Create a runtime role with no special privileges, with its password taken from your secret store (placeholder shown):
   `CREATE ROLE cfa_runtime LOGIN PASSWORD '<from your secret store>' NOSUPERUSER NOBYPASSRLS;`
2. Print the grants and run them as the database owner: `python -m cfa_tokenomics.admin app-role-sql cfa_runtime`. The role gets read and write on mutable tables and **insert and read only** on append-only history (assumptions and calculation nodes).
3. Point `CFA_DATABASE_URL` at the runtime role. Create a tenant as the owner with `python -m cfa_tokenomics.admin create-tenant NAME CURRENCY` and set `CFA_DEFAULT_TENANT_ID` to the id it prints (single-tenant installs).
4. `CFA_ALLOW_RLS_BYPASS=true` exists for development and test databases only. Never set it in production.

**Coverage.** Every tenant table is isolated, including the earlier usage ledger, role, grant, audit and checkpoint tables (migration `0008`). The audit log is append-only for the runtime role. Every data route runs in the installation's tenant, so `CFA_DEFAULT_TENANT_ID` is required: without it `/readyz` returns 503 (`tenant_not_configured`) and data routes refuse.

**Upgrading an install that already holds data.** Rows written before `0008` have no tenant, and nothing guesses one. They stay invisible, and `/readyz` returns 503 (`legacy_tenant_unassigned`), until the database owner names the tenant:

1. Take a recovery checkpoint, then run the migration: `python -m cfa_tokenomics.migrate upgrade`.
2. Create the tenant if needed (`create-tenant`), then run `python -m cfa_tokenomics.admin assign-legacy-tenant TENANT_ID` as the owner. It assigns every unassigned row in one transaction, makes `tenant_id` mandatory, and swaps the old global keys for tenant-scoped ones. It is safe to run again. An install with no rows needs no step: the migration finalizes it.
3. Optionally build the normalized usage facts: `python -m cfa_tokenomics.admin project-usage TENANT_ID`. It is idempotent and is not run automatically.

Downgrading `0008` fails, rather than merging data, if two tenants hold rows that share a key.

## Upgrades and removal

Version application, schema, archive format, provider adapters, and deployment contract separately where needed. Preview migrations, take customer-approved recovery checkpoints, test supported version transitions, and document rollback limitations for stateful changes.

Uninstall must distinguish runtime removal from deleting customer data. Default behavior must not silently destroy retained databases, archives, backups, or secret stores. A customer-authorized destructive option needs explicit scope and warnings.

## IaC and automation

Terraform or another IaC tool must be selected before claiming support. If Terraform is used, its backend, encryption, locking, permissions, and plans remain customer-controlled; marking a value sensitive does not automatically exclude it from state. See [HashiCorp sensitive data guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

Inherited `scripts/Initialize-Repo.ps1`, `scripts/initialize-repo.sh`, and `overlays/` are repository-template utilities, not platform installers. Do not run them against this customized project. Toolchain and CI cloud authentication choices remain separate from customer runtime authentication.
