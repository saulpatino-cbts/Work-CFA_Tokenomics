# Work-CFA_Tokenomics

Customer-hosted cloud and AI FinOps platform with Microsoft Foundry, Amazon Bedrock, and Google Vertex AI usage tracking, guided setup, role-based access, customer-approved assessments, and validated full-data import/export.

**Status: documentation and architecture foundation.** Application services, deployment packages, provider connectors, and product tests are not implemented yet. The capabilities below are requirements, not claims of a running or production-ready product. See [delivery status](docs/roadmap.md).

## Product boundaries

- Deploy the platform only in the customer's environment.
- Keep customer data, credentials, configuration, and operational telemetry under customer control.
- Support customer **admins**, **users**, and **readers** with server-enforced permissions.
- Give vendor administrators/support **no standing customer-data access**. A customer-authorized **Assessment** grants only explicitly approved scope for a limited period.
- Connect Foundry, Bedrock, and Vertex AI without requiring the customer to use all three.
- Measure model-token usage with provider-specific semantics, visible coverage, and no double-counting.
- Make setup clear, concise, resumable, and independently verifiable.
- Support full export/import with integrity, compatibility, relationship, and authorization validation.
- Leave retention, deletion, backup policy, and data ownership with the customer.

Customer-hosted does not mean no external processing: configured provider requests go to customer-approved cloud endpoints. Support access and any diagnostic transfer require separate, explicit authorization.

## Start here

| Audience | Read first |
| --- | --- |
| Product and architecture | [Requirements](docs/requirements.md), [architecture](docs/architecture.md), [decisions](docs/adr/README.md) |
| Customer administrators | [Deployment contract](docs/deployment.md), [guided setup](docs/onboarding.md), [data ownership](docs/data-ownership.md) |
| Security and support | [Roles and identity](docs/access-control.md), [Assessment access](docs/assessment.md), [security policy](.github/SECURITY.md) |
| Provider and FinOps engineers | [Provider integration](docs/providers.md), [token accounting](docs/token-accounting.md) |
| Migration and operations | [Export/import](docs/portability.md), [operations](docs/operations.md), [acceptance tests](docs/testing.md) |
| Contributors and maintainers | [Contributing](CONTRIBUTING.md), [agent instructions](AGENTS.md), [repository setup](docs/TEMPLATE.md) |

[Full documentation index](docs/README.md) · [Roadmap](docs/roadmap.md) · [Risk register](docs/risk-register.md) · [Changelog](CHANGELOG.md)

## Work with this repository

```bash
git clone https://github.com/saulpatinojr/Work-CFA_Tokenomics.git
cd Work-CFA_Tokenomics
git switch -c docs/your-change
```

Read the requirements and accepted ADRs before proposing implementation. There is no application install, start, or cloud deployment command yet. Do not treat template initialization scripts as product installers or rerun them against this customized checkout. Do not create cloud resources as part of documentation work.

The first implementation milestone is to choose the supported runtime/hosting profile and measurement mode, then build a minimal vertical slice with identity, roles, one provider adapter, usage persistence, and setup checks. All three provider integrations remain required for the product baseline; incremental delivery is not a scope reduction.

## Explicit exclusions

This baseline does not include subscriptions, payments, refunds, or other commercial operations. It does not impose vendor-owned deletion, a fixed vendor retention period, mandatory vendor telemetry, or a vendor credential repository. Earlier assumptions about iOS form processing, appointments, and a vendor-managed 90-day deletion workflow are not requirements for this repository.

## Repository governance

Use focused branches and pull requests. Preserve customer isolation, credential custody, and explicit Assessment consent in every change. Never commit real credentials, customer exports, account identifiers, prompts, or private infrastructure details.

Existing security/review configurations are inherited from the repository template. Their presence is not proof that third-party apps, private reporting, repository rules, or paid security features are enabled. See [maintainer setup](docs/TEMPLATE.md).

No license has been selected. Do not describe this project as open source or assume redistribution rights until the owner makes that decision. Report vulnerabilities using the [security policy](.github/SECURITY.md).
