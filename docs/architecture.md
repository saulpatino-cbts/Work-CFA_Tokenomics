# Logical architecture

**Status:** proposed component model constrained by accepted customer-hosted boundaries. No runtime, storage engine, frontend framework, or hosting service is selected here.

## Trust boundaries

| Boundary | Contents and authority |
| --- | --- |
| Customer environment | UI/API runtime, policy enforcement, workers, configuration, usage ledger, data stores, local observability, and secret references. |
| Customer identity provider | Human authentication and approved role/group claims; application authorizes every action. |
| Customer-approved provider endpoints | Foundry, Bedrock, and Vertex AI services accessed with customer-controlled identity. |
| Vendor support | No default customer-data access; temporary Assessment access only through customer-approved identity, route, and scope. |
| Software delivery | Versioned source/artifacts delivered for customer-controlled installation; not a standing execution channel. |

Customer-hosted is not equivalent to air-gapped. Provider calls, identity federation, update retrieval, and any approved diagnostic transfer require explicit network design and disclosure. Do not promise regional processing or private connectivity until verified for the chosen service/deployment.

## Proposed components

- **User experience:** setup wizard, connection health, permitted dashboards, export/import, and Assessment controls.
- **Application API:** resource authorization, validation, configuration, and workflow state transitions.
- **Identity/policy layer:** OIDC verification, role mapping, workload credentials, automation keys, and temporary grants.
- **Connector layer:** provider-specific discovery, telemetry, optional inference, pagination, retries, and normalization.
- **Usage ledger:** provenance-rich observations with stable deduplication and reconciliation semantics.
- **Job runner:** bounded collection, validation, migration, and customer-authorized lifecycle tasks.
- **Customer-local stores:** operational database/object data, secret references, audit records, and logs with explicit backup/export coverage.

These can initially share a deployable process where isolation and scale permit. Separate services are not a requirement.

## Data flow

1. Customer identity authenticates the user; the API evaluates installation/workspace/resource permissions.
2. An admin configures a provider using a local secret reference or workload identity.
3. The connector collects only approved data or observes requests explicitly routed through the application.
4. Normalization preserves source semantics; reconciliation prevents counting the same traffic twice.
5. Authorized views display usage, collection scope, freshness, and limitations.
6. Export/import operates inside the customer boundary unless the customer deliberately transfers an archive.
7. Assessment access is denied until an active customer grant and approved access route exist.

## Isolation and supply chain

Every query, job, cached response, archive, and support request must carry an enforceable resource scope. A dedicated installation does not eliminate isolation requirements between customer workspaces/users.

Pin and verify release artifacts; review migrations and permission changes before installation. A signed artifact is evidence of provenance, not proof that software cannot access customer data. Customers control upgrade approval and execution identities.

## Decisions before implementation

Select a supported hosting profile separately from the three provider integrations. Define internal API/data contracts before optimizing infrastructure. Record runtime, persistence, network, queue, and recovery choices through ADRs; do not present the inherited Terraform/Python/TypeScript overlays as selected architecture.
