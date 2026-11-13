# 0003. Provider accounting and full portability

- **Status:** Accepted requirement; contracts and formats proposed.
- **Date:** 2026-11-03
- **Decision authority:** Repository owner product clarification.
- **Requirements:** REQ-006, REQ-007, REQ-008, REQ-010.

## Context

The product must connect Foundry, Bedrock, and Vertex AI, account for their model-token usage, guide setup clearly, and support full validated import/export.

## Decision

Treat the three providers as independent required integrations. Preserve provider-specific usage semantics and show collection scope; do not imply that connecting a key captures every customer request. Full portability covers customer-owned application state with explicit secret/identity handling and validation before live changes.

## Alternatives considered

A single generic token sum loses source semantics. A CSV-only export does not restore complete customer-owned state. Blind database import can restore unsafe identities, active support access, and duplicated usage. These are insufficient implementations.

## Consequences

The platform needs versioned adapters, provenance, deduplication/reconciliation, clear setup checks, a consistent archive boundary, and safe identity remapping. Initial observation mode, archive format, secret migration, billing scope, and supported versions remain open.

## Validation

Exercise all three adapters with API-specific tests and authorized integration evidence. Demonstrate full export and restore into a fresh supported installation, including negative import tests. These capabilities are not implemented yet.

## Revisit trigger

New provider/API semantics, broader billing scope, changed archive format, or credential portability requirements need explicit compatibility decisions and migration tests.

## Amendment (2026-11-12)

The three providers (Foundry, Bedrock, Vertex AI) are no longer the whole source scope. [ADR 0010](0010-vendor-and-genai-scope.md) adds vendor APIs and Microsoft Copilot, and [ADR 0011](0011-ai-economics-platform.md) makes the product application-centric AI economics. The provider-specific accounting rules above, and the portability decision, still apply to every source. The "Initial observation mode" open item is decided by [ADR 0007](0007-observation-mode-and-reconciliation.md). This note changes no decision above.
