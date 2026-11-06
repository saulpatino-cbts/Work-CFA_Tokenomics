# 0006. Persistence

- **Status:** Proposed
- **Date:** 2026-11-06
- **Decision authority:** Product owner (approval pending)
- **Owners:** Architecture, Data
- **Requirements:** REQ-010, REQ-011
- **Issue:** No issue exists
- **Implementation evidence:** Pending; no database code exists.

## Context

The usage ledger, audit records, and role mappings need transactional storage that the customer can back up and export, on both clouds.

## Decision

Propose **PostgreSQL** (customer-managed service such as Amazon RDS or Azure Database for PostgreSQL), with versioned schema migrations. Secrets are referenced from the customer's secret store, never stored in the database in cleartext.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Cloud-native NoSQL per cloud | Managed scale | Two data models; harder portability (REQ-010) | One engine keeps export/import identical |
| SQLite | Simplest install | Weak concurrency, backup and HA story | Not suitable for a multi-user service |

## Consequences

Customers own backups and retention (REQ-011). Export/import must be built against the schema. Migration preview and recovery checkpoints are required before upgrades.

## Validation

Migration up/down tests and a fresh-restore test. None exist yet.

## Rollback or revisit trigger

Reopen if customer environments commonly cannot provide managed PostgreSQL.
