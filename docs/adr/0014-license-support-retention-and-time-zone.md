# 0014. License, support, retention and time zone

- **Status:** Accepted (owner statements of 2026-11-12, recorded as understood: proprietary license, no support commitment, client-chosen retention, UTC with an administrator-chosen time zone). The owner should confirm this wording. Legal text is not written: **[REVIEW REQUIRED]** by CBTS legal before any distribution.
- **Date:** 2026-11-12
- **Decision authority:** Owner
- **Owners:** Product; legal
- **Requirements:** REQ-001, REQ-009, REQ-011
- **Issue:** None exists
- **Implementation evidence:** time zone: `assume_timezone` in `apps/api/src/cfa_tokenomics/focus/parse.py` and the `--timezone` option of `import-focus`, tested in `tests/test_focus_parse.py`. Nothing else here is implemented: no license file, no retention controls, no administrator time zone setting.

## Context

[R-14](../risk-register.md) left the license and support policy undecided. [ADR 0013](0013-admin-only-product-and-per-user-cost.md) left retention open. Public FOCUS sample files write timestamps with no time zone, which the importer rejected until a rule was set.

## Decision

- **License: proprietary.** The software is not open source and no redistribution right is granted. The repository must not describe itself as open source. A license notice and any end-user terms need legal review **[REVIEW REQUIRED]**; none is drafted here.
- **Support: none promised.** No support level, response time or supported-version window is offered at this stage. Do not publish one in documentation, listings or code until the owner decides. A marketplace listing's support and pricing terms are a separate decision **[REVIEW REQUIRED]**.
- **Retention: the client's choice.** CBTS sets no retention timer and no deletion schedule. The client decides how long each class of data is kept and where long-term storage lives, and the product must be able to apply that choice. The configuration surface, the default and the long-term storage mechanism (for example archive to client-controlled storage) are **not designed yet**.
- **Time zone: UTC by default, administrator-selectable.** All instants are stored in UTC. A timestamp that states its own offset is never overridden. A timestamp with no offset is read as UTC unless the administrator chose another zone, and the zone assumed is recorded on each affected row (`_assumed_timezone`). An unknown zone is an error, never a silent fallback to UTC. The administrator's choice also governs how times are displayed.

## Alternatives considered

- Keep the strict rule (refuse timestamps without a zone). Safe but made the only public sample unusable.
- Silently assume UTC with no record. Simple but hides an assumption; provenance is a core rule.
- Open-source license. Not chosen by the owner.
- A fixed CBTS retention period. Conflicts with the customer-owned lifecycle boundary.

## Consequences

- README and CONTRIBUTING can state the proprietary license instead of "no license selected".
- The per-tenant administrator time zone setting, the retention settings and long-term storage need design and migrations (follow-on). Until then the zone is chosen per import (`--timezone`), defaulting to UTC.
- Named zones (for example `America/Chicago`) need the `tzdata` package, pinned in `pyproject.toml`; UTC and fixed offsets need nothing.
- Daylight-saving transitions make some local times ambiguous or non-existent; a named zone applied to an unzoned timestamp carries that residual uncertainty, which is why UTC is the default.

## Validation

The parser rule is covered by unit tests, run without a database. Not run here: the database-backed importer and connector tests. License text, support terms and retention behaviour have no validation yet.

## Revisit trigger

A decision to distribute outside CBTS clients, a client with a regulatory retention requirement, a source that mixes time zones in one file, or the first marketplace listing.
