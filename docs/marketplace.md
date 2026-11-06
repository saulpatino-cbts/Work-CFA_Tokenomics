# Marketplace distribution: gap analysis

**Status:** proposed plan and gap list. Nothing here is submitted, approved, or verified. Marketplace requirements change; items marked **[VERIFY]** were written from general knowledge and must be checked against the current AWS Marketplace Seller Guide and Azure Marketplace (Partner Center) publishing documentation before work depends on them. See [ADR 0005](adr/0005-container-packaging-and-marketplace.md).

## Intended model

Customers find the product in the AWS or Azure Marketplace, pull the container images, and run them in their own account/subscription. The GitHub `main` branch stays the source of truth; releases are cut from it. The marketplace is a delivery channel only: no vendor control plane, no vendor access to customer data ([REQ-001, REQ-004](requirements.md)).

## Easiest path for the customer (proposed)

1. Subscribe/accept the listing (free or private offer; terms are an owner decision).
2. Run a read-only **preflight** that checks identity, network, database and secret-store prerequisites.
3. Deploy with a customer-run template (CloudFormation on AWS, Bicep/ARM on Azure) that creates a container service, a PostgreSQL instance, a secret store reference, and ingress.
4. Open the setup wizard, create the first admin, connect providers ([onboarding](onboarding.md)).

## What exists today

| Area | State |
| --- | --- |
| Requirements, architecture, ADRs 0001-0003 | Documented |
| API skeleton (`apps/api`): health, config validation, role matrix, OIDC bearer verification, PostgreSQL role/audit layer, 45 tests (35 without a database) | Implemented, not a product |
| Dockerfile (skeleton), development-only compose | Exists; image build not run in this session (no Docker daemon) |
| ADRs 0004-0006 | Accepted by owner 2026-11-06; implementation pending |

## What is missing

| Gap | Needed before |
| --- | --- |
| OIDC verification and group-to-role mapping exist (unit-tested with locally signed tokens). Not done: test against a real IdP, JWKS fetch/caching behavior, last-admin protection (needs the database), automation API keys, UI sign-in flow | Exposing any route |
| PostgreSQL schema (role assignments, audit events), Alembic migration with downgrade, admin role routes with last-admin protection exist and pass tests against PostgreSQL 16. Not done: usage ledger tables, secret-store reference resolution (the URL is injected at runtime by the platform), backup/restore and upgrade tests on RDS/Azure Database, audit read/export | Any data feature |
| Usage ledger tables, replay-safe writes and reconciliation rules exist (ADR 0007, synthetic-data tests). Bedrock CloudWatch normalizer exists with no live calls. Not done: live collection and scheduler, request-capture path, Foundry and Vertex adapters, metric-name verification against provider docs, ledger API | Pilot |
| Web UI and setup wizard (none scaffolded) | Pilot |
| Export/import, Assessment grants and audit | Baseline completion |
| CI lint, test and image build exist (`api-ci.yml`, not yet run on GitHub); vulnerability scan, SBOM, image signing and provenance do not | Any release |
| Base image pinned by digest; dependency CVE review | Any release |
| Install templates and preflight for AWS and for Azure | Marketplace submission |
| Upgrade, rollback and recovery runbooks tested end to end | Marketplace submission |
| Licence decision (R-14); support contact and policy | Listing |
| Seller accounts, tax/banking profile, and listing assets (logo, description, docs, EULA) | Listing **[VERIFY]** |
| Marketplace-specific technical review: image scanning, no hardcoded secrets, documented usage instructions, supported regions/architectures **[VERIFY]** | Listing |
| Pricing/offer model and whether any marketplace metering is used (REQ-012 excludes commercial operations) | Listing |
| Decision on Azure offer type and AWS delivery method **[VERIFY]** | Packaging work |

## Rules that stay in force

No mandatory vendor telemetry or call-home in the images or templates. Installers send no secrets, plans, or customer data to the vendor. Customer controls upgrades. Do not claim marketplace availability until a listing is actually published.
