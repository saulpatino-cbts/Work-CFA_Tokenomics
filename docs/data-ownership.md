# Customer data ownership

**Status:** accepted product boundary; data controls are not implemented yet.

## Ownership and custody

The customer owns data and decides retention, deletion, backup, export storage, recovery, and authorized external processing. The product must expose understandable controls and document where data exists. Vendor ownership of the software does not confer access to customer data or credentials.

No vendor-enforced 90-day timer, vendor deletion attestation, mandatory diagnostic upload, or commercial-service lifecycle applies to this repository. A customer may choose retention rules, but the product must not invent legal mandates or silently choose policy on the customer's behalf.

## Required inventory

For each implemented data store, document owner, content categories, encryption/key custody, access paths, retention/deletion controls, backup behavior, export coverage, and restore implications. Include primary records, usage metadata, attachments if present, temporary files, caches, queues, audit records, archives, backups, and any approved provider-side persistence.

Do not collect prompts/completions by default. Usage metadata and account identifiers can still be sensitive; minimize, scope, and protect them. Sanitized operational telemetry stays customer-local unless the customer deliberately approves sharing.

## Division of responsibility

| Area | Product responsibility | Customer authority |
| --- | --- | --- |
| Data controls | Implement supported, documented mechanisms | Decide policy and execute/authorize actions. |
| Access | Enforce roles, scopes, and revocation | Manage users, groups, and role assignments. |
| Provider processing | Explain configured endpoints and known data flows | Approve accounts, regions, permissions, and processing terms. |
| Backup/restore | Provide supported procedures and compatibility | Configure schedule, keys, storage, retention, and restore approval. |
| Support | Enforce no-default-access Assessment | Approve identity, data scope, route, expiry, and revocation. |
| Software updates | Provide versioned artifacts and migration guidance | Approve and run changes. |

## Deletion and recovery

Deleting a live record is not automatically erasure from archives, logs, backups, versions, or provider stores. UI and runbooks must describe actual scope and limitations. Restoring older state must honor customer-approved deletion/revocation history before reopening access.

A deletion feature must identify affected data, dependencies, recoverability, and backup consequences. Do not promise proof of physical erasure the product cannot establish. Customer policy does not remove the product team's responsibility to implement accurate controls.

## External sharing

Normal operation must not depend on sending customer data to vendor services. Any optional telemetry, diagnostic bundle, or Assessment transfer must preview destination, purpose, payload categories, and custody. A transferred copy is outside the customer environment; disclose that fact explicitly.
