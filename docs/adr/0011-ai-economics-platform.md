# 0011. AI economics platform

- **Status:** Proposed
- **Date:** 2026-11-07
- **Decision authority:** Product owner
- **Owners:** Architecture, FinOps, Product
- **Requirements:** REQ-001 to REQ-012 (amended in part); proposed REQ-013 to REQ-022
- **Issue:** No issue exists
- **Implementation evidence:** None. This record and the [economics design set](../economics/README.md) are proposals; no code has changed.

## Context

The owner's brief states that the current application "has not fully hit the intended target". It answers *how many tokens were consumed*; the target answers *what an AI application costs to build and operate, what value it creates, and how it can be packaged and sold*. The [gap analysis](../economics/01-current-state-and-gap-analysis.md) finds no application entity, no cost model, a token-shaped ledger, shallow provenance, floating-point money, no value, scenario or pricing engine, no tenant isolation, and a connector contract too narrow for cost, seat and licence data.

## Decision

Reposition the product as an **application-centric AI economics platform** and design it as the [economics set](../economics/README.md) describes:

- The **Application** is the unit of analysis. Usage, cost, value, scenarios and price hang off it.
- **Raw ingestion, then normalization**, with versioned mappers and a connector framework that never assumes token telemetry.
- A **FOCUS-compatible cost model** (FOCUS 1.4; 1.5 token conventions adopted after ratification) and FinOps Foundation capability names.
- Every figure carries a **basis** (observed, estimated, assumed) and **finality**, and traces to its sources through calculation nodes.
- A pure, versioned **calculation engine** for cost, value, ROI, unit economics, scenarios, pricing and margin; exact decimal arithmetic.
- **Tenant isolation** in the schema from the first new table.

## What stays, changes and is superseded

| Record | Effect |
| --- | --- |
| [0001](0001-customer-hosted-boundary.md) customer-hosted boundary, [0002](0002-roles-and-assessment.md) roles | **Stay.** Vendor Assessment access is deferred, not removed from the principles. |
| [0003](0003-portability-and-provider-scope.md) three-provider scope | **Superseded in part:** provider scope becomes the connector framework; portability stays. |
| [0004](0004-application-stack.md), [0005](0005-container-packaging-and-marketplace.md), [0006](0006-persistence.md) | **Stay.** |
| [0007](0007-observation-mode-and-reconciliation.md) reconciliation | **Generalized** into overlap resolution across cost and usage. |
| [0008](0008-account-scoped-usage-access.md) scoping | **Stays**, re-scoped to tenant, business unit, application, environment. |
| [0009](0009-sku-source-dimensions-and-series.md) SKU and source | **Folded into** the FOCUS-based charge model. |
| [0010](0010-vendor-and-genai-scope.md) vendor scope | **Stays** and is extended by the connector matrix. |

REQ-012 ("no commercial operations") needs a clarification the owner must approve: **modelling** prices, margins and marketplace economics is in scope; payment processing, invoicing, subscription billing operations and marketplace metering are not.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Keep the token-centric design and add features | Reuses the most code | Cost, value and pricing would sit on a model that cannot hold them; provenance and tenancy retrofitted | The data model is the problem |
| Build economics as a separate product | Clean start | Duplicates identity, ingestion, security and delivery | The reusable plumbing is substantial |
| Adopt a proprietary FinOps model | Faster | The brief asks for FOCUS and FinOps Foundation alignment | Not selected |

## Consequences

Large scope increase, delivered in four phases with acceptance criteria. Value figures can be commercially sensitive, so the product must keep assumptions visible and basis labelled to remain credible. Per-user and prompt data raise privacy obligations (risk R-17). Several source APIs are in beta or have undocumented limits (R-21). Executives and finance become primary users, so the UI changes substantially.

## Validation

Per-phase acceptance criteria in the [roadmap](../economics/07-roadmap.md), including reproduction of the worked example, cross-tenant failure at the database, mapper determinism and explain-view traceability. None exists yet.

## Rollback or revisit trigger

Reopen if the owner narrows scope, if FOCUS 1.5 changes the token conventions adopted here, or if customers cannot provide the billing data the model depends on.
