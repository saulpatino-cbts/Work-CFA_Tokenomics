# 0012. Privacy modes for vendor usage sources: aggregate by default, per-user by recorded opt-in

- **Status:** Accepted (as read from the owner's reply of 2026-11-12, "can we do both?": support both modes, aggregate as the default and per-user as an opt-in; the owner should confirm this wording on review)
- **Date:** 2026-11-12
- **Decision authority:** Owner
- **Owners:** Security and privacy; connectors
- **Requirements:** REQ-013 to REQ-022 (proposed), customer data custody ([ADR 0001](0001-customer-hosted-boundary.md))
- **Issue:** None exists
- **Implementation evidence:** `apps/api/src/cfa_tokenomics/privacy.py` and `apps/api/tests/test_privacy.py` (the pseudonymizer and the mode type only). The Anthropic connector (`connectors/anthropic.py`) runs in aggregate mode, never groups by person and refuses person-level rows; it **refuses `per_user` mode because the pseudonymized storage for it does not exist yet**. No connector stores a pseudonym yet.

## Context

[Vendor API research](../economics/09-vendor-api-research.md) found that most vendor usage sources can identify people: Anthropic (Claude Code analytics, spend limits, per-user analytics), OpenAI and Codex (per-user daily rows with email, per-user monthly usage against caps), GitHub Copilot (per-user report files with logins), Microsoft 365 Copilot (per-user detail, credits per user), and Claude Code OpenTelemetry (`user.email`). Risk R-17 asked for a privacy review and a data-minimizing design. Several other sources hold prompt or conversation content and are out of scope for any mode.

The owner asked for both options: aggregate-only operation, and per-user detail where a customer wants it.

## Decision

1. **Every connector that can see people has two modes**, set per connector: `aggregate` (the default) and `per_user`.
2. **Aggregate mode never asks for person-level data.** The request itself leaves out the user dimension where the source allows it (for example OpenAI Daily Usage with `group=workspace`; no `actor` grouping for Anthropic; organization-level GitHub reports; Microsoft usage summaries rather than user detail). Anything identifying that arrives anyway is dropped before storage.
3. **Per-user mode is an explicit opt-in by an administrator.** Enabling it needs a written reason, records who and when in the audit log, and requires a retention period for the person-level rows (proposed default 90 days; the customer sets it). Roles other than administrator cannot enable it.
4. **Identifiers are pseudonymized at ingest, never stored in the clear.** A person's identifier (email, login, user id, account uuid) is replaced by `HMAC-SHA256(key, normalized identifier)`, truncated to 128 bits and prefixed `u_`, using a key the customer holds. The key is a secret-store reference resolved at runtime; it is never configured as a value, stored in the database, logged or sent to a browser. No table maps a pseudonym back to a person. The pseudonym is joinable across sources and over time while the key is unchanged, and **rotating the key deliberately ends that joinability**.
5. **The same identifier gives the same pseudonym in every source**, so a person's activity can be followed across vendors by someone who holds the key and the directory. Display names and emails are never stored alongside.
6. **Content-bearing sources are never connected in any mode:** Bedrock invocation logs, Vertex request-response logging, the Microsoft Copilot interaction export, the OpenAI Compliance API, and Azure request and response logs. Token counts come from metrics instead.
7. **Read-only credentials only.** Where a source exposes write operations next to read operations (for example OpenAI usage-limit updates, Compliance deletions), the connector's documented credential must be read-only.
8. **Raw payloads.** For per-user-capable API connectors the landed raw payload is the post-redaction payload (aggregate mode: the request excluded identities; per-user mode: identifiers already pseudonymized). **Known gap:** the manual FOCUS importer and the cost-export connectors keep the customer's export byte for byte, which can include the FOCUS 1.5 identity columns (`PrincipalId`, `CredentialId`, `RequesterDetails`) in the raw copy even though they are dropped from normalized rows. Closing it means redacting those columns before the raw copy is kept, which gives up byte-for-byte lineage for those columns. Tracked in R-17 as an open choice.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Aggregate only | Simplest, strongest privacy | No per-user cost or adoption; seat and licence analysis weak | The owner asked for per-user as well |
| Per-user always, in the clear | Easiest analysis | Stores emails and logins; large exposure; hard to justify to a customer | Conflicts with the data-minimizing principle |
| Per-user with an encrypted reversible map | Admin can look a person up | A stored map is a standing re-identification capability | Re-identification stays with the customer's own directory instead |
| Plain unkeyed hash | No key to manage | Emails are guessable, so the hash is reversible by anyone | Not a real pseudonym |

## Consequences

- **Customer hosting and credential custody:** the pseudonymization key is customer-held and referenced, not stored. No vendor or CBTS access is added.
- **Roles:** enabling per-user mode is administrator-only; readers and users see pseudonyms only.
- **Usage correctness:** pseudonymization does not change any total. Aggregate mode cannot answer per-person questions, and the product says so rather than approximating.
- **Operations:** key rotation breaks joins across the rotation boundary by design; the customer must plan for it. Losing the key means pseudonyms can no longer be recomputed from the directory.
- **Data lifecycle:** per-user rows carry their own retention; the customer owns deletion.
- **Not solved here:** the raw-copy gap in point 8, the choice of retention default, and the user interface for enabling the mode. Pseudonyms are personal data under some privacy laws if re-identification is reasonably possible; the customer's privacy review applies.

## Validation

- Pseudonyms are deterministic for a key, differ across keys, are not reversible without the key, never contain the identifier, and normalize case and surrounding whitespace (tested in `test_privacy.py`).
- Each connector, when built, has a test that its aggregate mode sends no user dimension and stores no identifier, and that its per-user mode stores only pseudonyms.
- Untested assumptions: that a 128-bit truncated keyed hash is adequate for the customer's threat model, and the 90-day default.

## Rollback or revisit trigger

Revisit if a customer's privacy review rejects keyed pseudonyms, if a vendor exposes identity in a way that cannot be dropped, or when the raw-copy gap is decided.
