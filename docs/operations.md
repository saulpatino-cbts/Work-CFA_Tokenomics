# Day-two operations

**Status:** proposed operational contract. Executable runbooks must be added with the selected runtime; no recovery or support SLA is established here.

## Customer-local observability

Track health, collection lag, failed permissions, credential expiry, queue/backlog, import/export progress, rejected observations, reconciliation differences, and software versions. Use scoped correlation identifiers; do not record secret values or prompt/completion content. Restrict diagnostic detail by role.

A healthy process is not proof of complete usage collection. Show last successful sync and source scope beside usage totals. Alerts must have customer-configurable destinations and actionable remediation.

## Required runbooks

| Runbook | Required evidence |
| --- | --- |
| Credential rotation | Replace locally, verify access, revoke old identity/key, no vendor exposure. |
| Provider outage/throttling | Bounded retries, resumable checkpoints, visible partial coverage. |
| Identity lockout | Customer-controlled recovery without vendor master credentials. |
| Failed install/upgrade | Identify partial resources/state and resume, roll forward, or restore safely. |
| Backup/restore | Restore into isolation; verify integrity, authorization, and revoked/deleted-state handling. |
| Assessment incident | Revoke grant/route, stop ongoing access, preserve minimal local audit evidence. |
| Usage discrepancy | Compare source/window/grain and normalization versions without double-counting. |
| Import/export failure | Preserve original data, reveal incomplete status, provide a recovery path. |
| Customer deletion | Confirm scope, dependencies, backup limits, and customer authority. |

## Recovery targets

Customer requirements and measured tests must establish acceptable recovery time, data loss, and collection backlog. Do not choose multi-region infrastructure or publish quantitative guarantees without a justified target.

Backups and full portability are complementary: an archive format does not replace operational recovery, and a database backup alone does not prove full cross-environment migration.

## Release operations

Record compatible application/schema/archive/adapter versions, migration plan, permission changes, external destinations, known issues, and recovery procedure. Customers choose upgrade timing. Do not enable an implicit remote vendor execution/update channel.

If ordinary operation requires outbound checks, document exact purpose and payload. Disable unapproved telemetry, analytics, and diagnostic uploads. Third-party development/review tools must never receive customer exports or runtime secrets.

## Responsibility

Customer operators control installation, provider accounts, data policy, and recovery approval. Maintainers deliver correct software, documented limitations, migration guidance, and supported fixes. Vendor support receives only the access explicitly approved through [Assessment](assessment.md).
