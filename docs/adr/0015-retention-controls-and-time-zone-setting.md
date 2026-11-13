# 0015. Retention controls and the administrator time zone setting

- **Status:** Proposed. Needs the owner's decision on the questions below before any code is written.
- **Date:** 2026-11-13
- **Decision authority:** Owner
- **Owners:** Data and operations; security
- **Requirements:** REQ-011, REQ-021
- **Refines:** [ADR 0014](0014-license-support-retention-and-time-zone.md)
- **Issue:** None exists
- **Implementation evidence:** none. Design detail is in [retention and time zone design](../economics/13-retention-and-time-zone-design.md).

## Context

ADR 0014 says retention is the client's choice and the time zone is UTC unless an administrator chooses one. Neither is built: there is no retention control and no stored time zone. Most data tables are append-only for the application role, so a purge cannot use the normal database credentials.

## Decision (proposed)

**Time zone**

- One tenant setting `timezone` (default `UTC`, IANA names only), admin-write and audited.
- Precedence for an unzoned timestamp: explicit per-import or per-connector zone, then the tenant setting, then UTC. A stated offset always wins.
- A change is not retroactive; stored rows keep the zone recorded when they were imported. Day buckets accept a zone and the API keeps returning UTC.

**Retention**

- Per-tenant, per-layer policy (raw files, cost facts, usage, calculations, audit, people). **No policy means keep indefinitely**, and the product says so. It never chooses a period.
- A purge is an operator-run command, dry run by default, with a separate least-privilege database role that can delete only policed layers for one tenant. The application role's append-only grants do not change.
- Legal hold on a layer blocks purging it.
- Optional archive-before-delete to client-controlled storage; cost facts archive as gzipped FOCUS CSV, which the importer can re-read.
- Whole billing periods are purged oldest first with their superseded history; calculation trees are purged whole.
- Every run is audited (counts only). The UI and runbook state that deletion is not erasure from backups, archives or logs.

## Alternatives considered

- A background retention timer in the application: it would delete on a schedule the client may not expect, and it would need delete rights on append-only tables. Rejected.
- A fixed default period (for example 13 months): the product would be choosing policy for the client, which ADR 0014 rules out. Rejected.
- Making the append-only tables deletable by the application role: removes the protection against a bug or stolen credential. Rejected.
- Soft delete (hide, keep): does not meet a client's wish to remove data. Rejected as the only option; a hold or archive can still keep data deliberately.

## Consequences

Two migrations (`0012` time zone, `0013` retention policy and run history), a new database role and generated grant SQL, a new admin command, and new documentation of exactly what a purge does and does not remove. Archive verification needs a real bucket or container (not available yet). Retention screens wait on brand approval.

## Questions for the owner

1. Is "no policy means keep indefinitely" right as the default?
2. May a client set a retention shorter than a source's own revision window (the next import could bring the purged period back)? Proposed: warn and require confirmation.
3. Should the audit layer have a floor, or stay fully the client's choice with a warning? Proposed: client's choice with a warning.
4. Archives: format (gzipped FOCUS CSV proposed), who holds the keys, and whether the product encrypts them or leaves that to the storage account.
5. Order of work: time zone first (small), then retention policy and dry run, then deletes. Agreed?

## Validation

Per slice, in the design document: restricted-role tests, an application role that still cannot delete, a retention role that cannot cross tenants or touch an unpoliced layer, dry run changes nothing, legal hold blocks, totals stay consistent after a purge, and the explain view still verifies. Not validated yet: anything.

## Revisit trigger

A client with a regulatory retention or deletion requirement, the first multi-year install, the full export/import design, or a connector whose source revises data for longer than expected.
