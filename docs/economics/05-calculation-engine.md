# 5. Calculation engine

**Status:** proposed methodology. Part of the [AI economics redesign](README.md). Worked-example figures are **illustrative, not provider prices or marketplace fees**.

> **Implementation.** Sections 1 to 10 are implemented as a pure library in `apps/api/src/cfa_tokenomics/econ` (`formulas.py`, `commercial.py`, `scenario.py`, `node.py`), tested in `apps/api/tests/test_econ.py`, including the worked example below reproduced exactly. Overlap resolution (section 10) and allocation (section 2) need the database layer and are not yet implemented.

## Rules that apply everywhere

- Exact decimal arithmetic; currency carried on every amount; no summing across currencies (convert first with a stored, dated `FxRate`).
- Each formula has an ID and version (for example `tca.v1`). Results record both ([provenance](#provenance-and-basis-propagation)).
- Every input has a `basis`: `observed`, `estimated` or `assumed`. Estimates are never shown as telemetry.
- Calculation is a pure library: inputs in, a tree of calculation nodes out. No database access, no clock, no randomness (Monte Carlo uses a stored seed).
- **Observed beats estimated.** For a given charge, an observed billed cost replaces a computed estimate; the difference is kept as a variance, never added.

## 1. Usage to AI model cost

Let `Q(a,t,p,m,k)` be the quantity of billable measure `k` (input, output, cache read, cache write, reasoning, requests, seats) for application `a`, period `t`, provider `p`, model `m`.

```text
AICost_est(a,t) = sum over (p,m,k)  Q(a,t,p,m,k) * Price(p,m,k,t)
```

- `Price` comes from the `PriceBook` entry effective at `t` (list, negotiated, or derived from observed bills). Each entry carries an **inclusion rule** stating whether a measure is already counted inside another (for example cached tokens inside input) so a quantity is never priced twice. Providers define these differently; the rule is data, not code.
- Where an observed billed cost is allocated to `(p,m,t)`, `AICost = AICost_obs`; otherwise `AICost = AICost_est`. Variance `V = AICost_obs - AICost_est` is reported wherever both exist. Mixing observed and estimated for the same charge is not allowed.

## 2. Infrastructure, licence and supporting cost

```text
InfraCost(a,t)   = sum over cost lines c  AllocatedEffectiveCost(c,a,t)     [compute, storage, network, supporting APIs]
LicenceCost(a,t) = sum over licence lines  AllocatedAmount(l,a,t)           [seat or subscription, by seats used or assigned]
```

- The default measure is **effective cost** (after discounts, with commitments amortized). Billed and list cost are shown alongside so commitment benefit is visible. Names and definitions follow FOCUS ([data model](03-data-model.md#focus-alignment)).
- **Allocation** assigns each cost line `c` with amount `X_c` to applications by the first matching rule in priority order: tag, direct mapping, proportional by a usage driver (`share_a = driver_a / sum driver`), fixed percentage, or even split. Invariant, enforced and tested: `sum over a AllocatedCost + Unallocated = X_c`. Unmatched cost goes to a visible *unallocated* bucket. Allocation quality (the share allocated, and how) is reported next to every application total.

**Implemented (Phase 1 slice 4)** in `alloc/` (`engine.py`, `runner.py`):

- **Rules** are versioned and append-only, ordered by priority; the first rule whose conditions match **and that can be applied** wins. Methods: `direct`, `tag` (tag value names an application, or an explicit map; case-sensitive; a value-less tag cannot name one), `fixed_percent` (a remainder goes to *unallocated* with reason `percent_remainder`), `even`, and `proportional` (explicit, versioned driver values per application and period; every listed application must have a driver, otherwise `driver_missing`). A matching rule that cannot be applied falls through; the first such reason is kept as the unallocated reason (`tag_missing`, `tag_unmapped`, `tag_without_value`, `driver_missing`, `driver_zero`, `no_rule`).
- **Exact splitting.** Amounts are split in integer units of 10^-18 by the largest-remainder method, ties by position, so the slices add up to the original in all four measures (billed, effective, list, contracted) with no rounding drift. This does not depend on the process's decimal precision (a hidden-rounding bug of that kind was found and fixed during development).
- **Runs.** A run covers current cost lines whose charge period starts in a half-open window, in one transaction, and is skipped when an identical run (rules, drivers, cost lines) already succeeded. "Current allocation" of a line is the slices of the latest successful run (by sequence number, never by clock).
- **Reports** keep three buckets apart per currency: allocated, explicitly unallocated (with reasons), and **not yet allocated** (for example after a revised import). Coverage is allocated effective cost over total effective cost. `verify_allocation` lists any line whose slices do not add up; it must be empty. `python -m cfa_tokenomics.admin allocate TENANT START END` runs and summarizes.
- **Not built:** deriving proportional drivers from usage records (drivers are entered or imported), workload-level and customer-level rules beyond a fixed workload on a direct rule, shared-cost pools, and an API or screen.

## 3. Operations and development

```text
Ops(a,t) = OpsHours(a,t) * LoadedRate          (assumed unless support cost is observed and allocated)
Dev(a,t) = InitialInvestment / N               for each of N months after go-live (straight-line; configurable)
```

## 4. Total Cost of Application

```text
TCA(a,t)     = AICost + InfraCost + SupportingAPICost + LicenceCost + Ops + Dev
RunCost(a,t) = TCA(a,t) - Dev(a,t)             (operating cost, excludes amortized build cost)
```

Both are kept because they answer different questions ([ROI](#7-roi-and-payback) uses `TCA`; payback uses `RunCost`).

## 5. Unit economics

```text
UnitCost_u(a,t) = TCA(a,t) / Units_u(a,t)      for u in { transaction, AI interaction, active user, customer, business outcome }
Marginal cost   = variable cost / interactions  (AI cost + variable infrastructure)
```

Units come from observed `UsageRecord`s or `BusinessMetric`s where they exist; otherwise they are assumptions and are labelled so. A *run-cost-only* variant is shown beside the fully loaded one. Fixed and variable cost are split explicitly because scenarios scale them differently.

## 6. Business value

For application `a`, period `t`, with `T` transactions:

```text
HoursSaved   = (BaselineHoursPerTxn - AssistedHoursPerTxn) * T * Adoption * Realization
LaborValue   = HoursSaved * LoadedRate
ErrorValue   = (BaselineErrors - AssistedErrors) * CostPerError
CycleValue   = DaysSaved * CarryingCostPerDay * Volume
RevenueValue = RevenueUplift * ContributionMargin           (not gross revenue, unless stated)
AvoidedCost  = sum of entered items
BusinessValue = LaborValue + ErrorValue + CycleValue + RevenueValue + AvoidedCost
```

- `Realization` (0 to 1) and `Adoption` are explicit assumptions, not hidden constants.
- **Capacity value versus cashable value.** Hours saved are capacity; they become cash only if headcount, overtime or contractor spend changes. The model reports both: `CashableValue = CapacityValue * CashabilityFactor`, with the factor an editable assumption. Executives see which figure a claim rests on.
- `LoadedRate = AnnualSalary * (1 + BurdenRate) / ProductiveHoursPerYear`, all editable.

## 7. ROI and payback

```text
NetValue   = BusinessValue - TCA
ROI        = NetValue / TCA
Payback    = InitialInvestment / MonthlyNetBenefit,   MonthlyNetBenefit = BusinessValue_month - RunCost_month
```

Payback uses `RunCost`, not `TCA`, because `TCA` already contains the amortized investment; using `TCA` there would count the build cost twice. If `MonthlyNetBenefit <= 0` payback is reported as "not reached", not a number. Optional: NPV and IRR over a stated horizon and discount rate.

## 8. Scenarios and forecasting

A scenario is a set of **driver overrides** on a base scenario. Drivers form a tree:

```text
Tokens(k)  = Users * Adoption * InteractionsPerUser * TokensPerInteraction(k) * ModelMix(m)
AICost     = sum over (m,k) Tokens(k) * Price(m,k)
Infra      = Fixed + VariableRate * Load + sum over steps ceil(Load / Capacity) * StepCost
Committed  = Commit + max(0, UsageAtCommitRate - Commit) at the overage rate     (waste = unused commitment)
```

Scenario kinds: **Baseline** (reference state), **Current** (anchored to observed data; assumptions shown), **Forecast** (drivers projected), **Optimized** (forecast plus levers such as model change, caching, commitment), **Customer Proposal** (priced for one customer). Each scenario recalculates AI spend, infrastructure spend, total cost, unit cost, business value, ROI, required price and gross margin through the same library as *Current*.

**Sensitivity.** One-at-a-time ranges on adoption, token volume, model choice, cloud rates, labor rate and price (tornado ranking on ROI, margin, required price), and two-way grids. Monte Carlo with stated distributions and a stored seed is a later option. Only assumed inputs get uncertainty ranges; observed inputs do not.

**Cost forecasting and budgets** (FinOps capabilities) use the driver model first. Time-series extrapolation is allowed only as an `estimated` baseline and is labelled so. Budget variance is `Actual - Budget` with the same basis labelling.

## 9. Commercial pricing and margin

```text
Revenue      by price model: subscription, per user (U * p), usage (sum Q_k * p_k), per transaction (T * p), token-based,
             application flat fee, tiered (graduated: sum over tiers min(max(Q - lo,0), hi - lo) * p_tier), customer-specific
MarketplaceFee = FeeRate * Revenue + FixedFee            from the fee schedule effective at the date (configuration)
NetRevenue   = Revenue - MarketplaceFee
COGS         = RunCost attributable to the customer or offering (variable + allocated fixed + support)
GrossMargin  = (NetRevenue - COGS) / Revenue
```

Required price for a target margin `m` with proportional fee `f`:

```text
Price = COGS / (1 - f - m)                                (infeasible if 1 - f - m <= 0)
UnitPrice = (VariableUnitCost + FixedCost / N) / (1 - f - m)
BreakEvenVolume N* = FixedCost / (UnitPrice * (1 - f) - VariableUnitCost)
```

**Marketplace and commitment economics are configuration.** Fee rates, fixed fees, tiers, effective dates, and the share of a private offer that draws down a customer's cloud commitment (`commitment_drawdown_eligibility`, 0 to 1) are stored per offering and never hard-coded. A customer-side effective price can be shown as `Price * (1 - eligibility * ValueOfCommitBurn)`, where the last term is an explicit assumption. Actual marketplace terms must be read and entered by the user; the product does not assume them.

## 10. Overlap resolution

Generalizes the reconciliation built for token counts ([ADR 0007](../adr/0007-observation-mode-and-reconciliation.md)). The same charge can appear in several sources (for example a model used through a cloud platform also shows in the model vendor's own usage API).

1. A **charge identity** is `(billing owner, service, account, period)`. The billing owner is the party that invoices the charge.
2. Sources are ranked by authority: invoice-grade billed cost, then vendor or cloud cost export, then metric-derived estimate, then price-book estimate.
3. Totals use the highest-authority source available for each charge identity. Lower-ranked sources are kept as shadow records for variance and sanity checks and are **never summed with the winner**.
4. Usage-only sources (tokens, requests) do not create cost; they explain it and drive allocation.

## Provenance and basis propagation

Each node stores its inputs. The basis of a derived figure follows these rules:

- **Sums:** basis mix is the value-weighted mix of the parts (for example "62% observed, 30% estimated, 8% assumed").
- **Products and ratios:** basis is the weakest input (`observed` < `estimated` < `assumed`), shown conservatively.
- A figure with any assumed input is labelled assumption-dependent.

The explain view walks **number, calculation, input, source, timestamp** and shows the formula ID and version, the price-book version, the raw record and ingestion run, and the basis mix.

## Worked example (illustrative figures)

Application A, monthly. Prices, rates and fees below are placeholders for the arithmetic.

| Item | Value | Basis |
| --- | --- | --- |
| Input tokens 40M at $3 per 1M; output tokens 10M at $15 per 1M | AI cost $270 | estimated (price book) |
| Infrastructure | $600 | observed (allocated cost export) |
| Licences | $200 | observed |
| Operations: 10 h at $90 | $900 | assumed |
| Development: $120,000 over 24 months | $5,000 | assumed |
| **TCA** | **$6,970** | mixed |
| **RunCost** (TCA less development) | **$1,970** | mixed |

Value: 1,500 transactions, 0.5 h before, 0.2 h after, realization 0.7, loaded rate $85. Hours saved = 0.3 × 1,500 × 0.7 = 315 h. **Capacity value = $26,775.**

| Measure | Capacity basis | Cashable basis (25%) |
| --- | --- | --- |
| Business value | $26,775 | $6,694 |
| Net value (value less TCA) | $19,805 | -$276 |
| ROI | 284% | -4.0% |
| Monthly net benefit (value less RunCost) | $24,805 | $4,724 |
| Payback on $120,000 | 4.8 months | 25.4 months |

The same application looks excellent or marginal depending on whether hours saved convert to cash, which is why the product exposes that assumption.

Pricing: with RunCost $1,970 as COGS, a 3% proportional fee (illustrative) and a 40% target margin, `Price = 1,970 / (1 - 0.03 - 0.40) = $3,456` per month. Check: net revenue is 3,456 × 0.97 = 3,352; less the 1,970 COGS that is 1,382; and 1,382 / 3,456 = 40%.

Scaling: 10× users and 10× tokens at the same prices makes AI cost $2,700 (linear in tokens); infrastructure follows its step function; a cheaper model or caching changes `Price(m,k)` and `ModelMix`; a commitment trades a lower rate for waste risk when usage falls short. All of it recalculates through the same formulas.

## HTTP API (implemented, Phase 1 slice 5)

All routes are under `/v1`, run in a tenant-scoped session and need `economics:read` (reader, user, admin) or `economics:write` (user, admin). Decimals are sent as strings or integers; a float is refused with 422. Writes are audited.

| Route | Purpose |
| --- | --- |
| `POST /applications`, `GET /applications`, `GET /applications/{id}` | Application records (currency, lifecycle, investment with its basis). |
| `PUT /applications/{id}/assumptions/{key}` | Appends a version. A rationale is required; `value: null` means unknown, never zero. |
| `GET /applications/{id}/assumptions`, `.../{key}/history` | Current values and the full history with authors. |
| `PUT /allocation/rules/{key}`, `POST /allocation/rules/{key}/drivers` | Versioned rules and driver values ([allocation](03-data-model.md#pricing-and-allocation)). |
| `POST /allocation/runs`, `GET /allocation/summary` | Run a window (idempotent) and read coverage per currency. |
| `POST /applications/{id}/scenarios/evaluate` | Runs the scenario engine on drivers that each carry a value, a basis and an optional source. Optional `sensitivity` (a tornado over named drivers) and `save_as`. Returns every figure with its node id and basis mix. |
| `GET /cost/ai-tokens?start=&end=` | AI tokens, cost, model, direction, cache action, input-to-output ratio and cache hit rate read from imported FOCUS rows ([FOCUS 1.5 AI Model Billing](08-focus-1-5-readiness.md)). Needs only `economics:read`. Rows missing a model or direction are counted, not guessed. |
| `GET /explain/{node_id}` | The calculation tree down to its inputs, re-verified against its content hash. A stored node that no longer matches returns 500. Another tenant's node and an absent one both return 404. |

Limits worth knowing: the scenario currency must equal the application's; model shares must sum to 1; a model with no price for a token category is an error, not a zero; the tornado accepts at most 25 drivers per request. Not implemented: per-application scoping ([R-25](../risk-register.md)), listing or loading saved scenarios, and comparing an estimate with an observed bill.
