# Risk and decision register

**Status:** design-stage risks, not observed production defects. P0 blocks the affected implementation/release path; P1 blocks broader readiness. Owners below are responsibility areas, not an appointed or staffed team.

| ID | Priority | Open issue | Proposed owner | Closure evidence |
| --- | --- | --- | --- | --- |
| R-01 | P0 | Initial hosting/runtime and persistence: ADRs 0004-0006 proposed, not accepted | Architecture | Accepted ADRs with install and recovery implications, and a tested install. |
| R-02 | P0 | Assessment route into private installations unresolved | Security/platform | Approved transport, no standing access, tested revoke/expiry. |
| R-03 | P0 | Observation coverage undecided | FinOps/connectors | Explicit source/grain/scope and reconciliation design. |
| R-04 | P0 | Role scopes and first-admin recovery need approval | Identity | Permission contract and direct API denial tests. |
| R-05 | P0 | Full export secret/identity migration policy open | Security/data | Explicit exclusions or approved encrypted mechanism; no privilege restoration. |
| R-06 | P0 | Provider token fields differ and may overlap | Connectors | Versioned normalization fixtures and tests per API/model. |
| R-07 | P1 | Repeat installs/upgrades can leave inconsistent state | Platform | Resumability, migration, rollback/recovery tests. |
| R-08 | P1 | Customer ownership mistaken for absence of lifecycle features | Product/data | Supported backup/export/delete controls and actual limits documented. |
| R-09 | P1 | Aggregates misrepresented as user/request usage | FinOps | UI shows provenance, grain, freshness, and attribution limits. |
| R-10 | P1 | Exports/imports replay jobs or resurrect access | Data/security | Snapshot boundary, worker fencing, grant/session invalidation tests. |
| R-11 | P1 | External telemetry/review tools receive customer content | Security | Egress/payload inventory and approved optional sharing only. |
| R-12 | P1 | Inherited template scripts overwrite customized README | Maintainers | No reruns; archive/remove them when repository tooling is intentionally implemented. |
| R-13 | P1 | Repository rules, private reporting, and integrations unverified | Maintainers | Settings verified through maintainer checklist; no invented green checks. |
| R-14 | P1 | License and release support policy undecided | Owner | Explicit license/support decision before distribution. |
| R-15 | P1 | Billing, negotiated rates, and estimate scope unclear | Product/FinOps | Approved feature scope and source/currency/provenance rules. |

## Change discipline

A closed risk requires links to a decision and implementation/test evidence. Documentation alone may close a policy decision, not prove a runtime control. Do not mark risk accepted on behalf of the customer or repository owner without approval.

Changes to accepted boundaries require a superseding ADR. Reassess the register when new hosting targets, external destinations, provider APIs, or support capabilities are introduced.
