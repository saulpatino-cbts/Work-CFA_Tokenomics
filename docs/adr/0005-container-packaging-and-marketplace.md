# 0005. Container packaging and marketplace distribution

- **Status:** Accepted (owner approval 2026-11-06); implementation pending
- **Date:** 2026-11-06
- **Decision authority:** Product owner
- **Owners:** Platform
- **Requirements:** REQ-001, REQ-002, REQ-004, REQ-009, REQ-012
- **Issue:** No issue exists
- **Implementation evidence:** Pending; only a skeleton `apps/api/Dockerfile` and a development-only compose file exist.

## Context

Customers are expected to obtain the product from the AWS Marketplace or Azure Marketplace and run it in their own environment. The GitHub repository `main` remains the source of truth. Resolves part of R-01 and R-07.

## Decision

Propose: build **one OCI image set from `main`**, signed and with an SBOM and provenance, and package it per marketplace:

- **Azure:** an Azure Marketplace offer type to be selected ([VERIFY] container offer vs. managed application) that deploys into the customer's subscription.
- **AWS:** an AWS Marketplace container product ([VERIFY] delivery method) deployed with customer-run CloudFormation into the customer's account.

Marketplace is a **delivery channel only**. It must not become a vendor data or control plane (REQ-001, REQ-004). Marketplace metering or listing fees are commercial operations and out of scope (REQ-012); the listing terms (free or private offer) are a separate owner decision.

## Alternatives considered

| Alternative | Benefits | Drawbacks | Reason not selected |
| --- | --- | --- | --- |
| Azure-first only | Faster first listing | Defers AWS customers | Both clouds expected; shared containers keep cost low |
| VM image per cloud | Simple for customers | Two images to patch, larger attack surface | Containers share one artifact |

## Consequences

Each cloud needs its own install template (identity, network, database, secrets) around the same images. Installers must run preflight and send nothing to the vendor implicitly (see [deployment](../deployment.md)). See [marketplace gap analysis](../marketplace.md).

## Validation

A fresh install from the listing into a test account, health checks, upgrade and recovery test, and image signature verification. None exist yet.

## Rollback or revisit trigger

Reopen if a marketplace's terms require vendor-side metering, telemetry, or a control plane.
