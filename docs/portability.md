# Full export and import

**Status:** required capability with a proposed archive and validation contract. Format, encryption mechanism, size limits, and cross-version support remain open decisions.

## Meaning of full

Export must cover customer-owned state needed to restore the platform: records, attachments, derived data, workspaces, configuration, dashboards, provider definitions, usage observations, provenance, audit history under customer policy, collection checkpoints, and schema/application versions. Explicitly enumerate exclusions and unfinished jobs. A chart CSV is not a full export.

Proposed default: preserve connection definitions and secret references but exclude live credentials, sessions, automation keys, and active Assessment authority. Require customer reauthorization after import. If secret portability is required, design a separately approved encrypted customer-controlled mechanism rather than weakening the default archive. This is an open decision, not a silently omitted requirement.

## Proposed archive manifest

Record format version, application/schema version, export ID, UTC snapshot boundary, collection watermarks, object inventory/counts, file checksums, relationships, supported import range, exclusions, and encryption metadata without secret values. A checksum proves integrity against its trusted reference, not authenticity of an untrusted archive.

Provide a consistent snapshot or quiesce writes. Explain in-flight job handling. Customer controls encryption keys and storage location. Do not automatically upload archives to the vendor.

## Validation pipeline

1. Validate authorization and permitted import mode.
2. Check archive safety: size, decompression bounds, path traversal, links, file types, and resource limits.
3. Validate manifest, completeness, checksums, and schema compatibility.
4. Check uniqueness, references, attachment relationships, required fields, units, timestamps, and usage semantics.
5. Map source identities/groups and resources to the destination without elevating permissions.
6. Produce a dry-run: creations, merges, replacements, conflicts, exclusions, and rejected records.
7. Stage data; commit atomically where feasible or use checkpoints and a documented recovery path.
8. Verify counts, checksums, relationships, authorization, and core application behavior.
9. Reauthorize connections and resume collection only after deduplication/cursor checks.

Dry-run must have no live configuration, provider, role, or job side effects. Reject unsafe/incompatible imports before partial live-state changes. Silent record dropping is not validation.

## Authority and identity safety

Never reactivate sessions, historical support grants, automation keys, invitations, or old role assignments without destination approval. Preserve audit history as history and retain current target administration control. Email alone is not a safe cross-environment identity mapping.

Define empty-restore and merge modes separately. Scope mapping and ID collision behavior must be deterministic. Repeated imports must either be safely idempotent or explicitly rejected, never double-count usage.

## Cutover and evidence

Fence old collectors/workers before the restored installation starts collecting. An old cursor must not replay already imported observations into duplicate totals. Record the export/import boundary and validate source/destination counts and relationships.

Required tests include corrupted/missing attachments, incompatible schema, truncated archive, hostile paths, decompression limits, identity collisions, repeated imports, interrupted commit, and a fresh-environment restore without secret leakage.
