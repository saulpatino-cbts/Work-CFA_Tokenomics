# Security policy

## Reporting privately

Use GitHub private vulnerability reporting **if enabled** for this repository: [security reporting](https://github.com/saulpatinojr/Work-CFA_Tokenomics/security/advisories/new). Its availability has not been verified. Do not open public issues with exploit details, credentials, customer data, private endpoints, or sensitive account information.

If private reporting is unavailable, open a minimal issue requesting a private contact method from the maintainer without describing the exploit. No verified private email or guaranteed response-time SLA is established. Repository maintainers are identified in [CODEOWNERS](CODEOWNERS).

Only test systems you own or are explicitly authorized to assess. A software repository is not authorization to test customer environments or provider accounts.

## Scope

Report defects in identity/authorization, support Assessment, credentials, data isolation, imports/exports, provider endpoints, normalization/data integrity, deployment/migrations, dependencies, CI/release artifacts, and logs/telemetry. A documented design risk does not excuse a working bypass or broader vulnerability.

Include affected commit/version, impact/preconditions, sanitized reproduction, and minimal safe evidence. Never attach customer archives, raw prompts/completions, live credentials, or identifiable provider payloads.

## Product boundaries

Customer-hosted software must not require vendor-held secrets or standing vendor data access. Customer roles and temporary Assessment grants must be enforced server-side. Full imports must not revive historical sessions/grants or introduce privilege escalation. Customer controls retention and deletion; the product must accurately describe its mechanisms and limits.

## Secret exposure

Treat an exposed secret as compromised. Notify the customer/authorized owner through a private route, revoke or rotate locally, and preserve minimum evidence. Removing a value from the latest file does not remove historical exposure. Do not copy the secret into a public report or support transcript.

## Supported versions

| Version/branch | Status |
| --- | --- |
| `main` | Pre-release documentation/design; reports accepted, no production-support guarantee. |
| Released product versions | None published by this documentation baseline. |

Maintainers must publish supported release ranges and a verified reporting channel before production distribution. Do not represent inherited scanners or unverified repository settings as security certification.

## Coordination

Maintainers triage based on severity and available evidence without a promised SLA. Coordinate disclosure privately. Customer incidents remain customer-controlled; vendor investigation still requires explicit Assessment or another separately authorized access path.
