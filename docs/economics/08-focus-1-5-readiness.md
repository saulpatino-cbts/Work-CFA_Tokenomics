# 8. FOCUS 1.5 readiness

**Status:** preparation note, written 2026-11-07 ahead of the FOCUS 1.5 release scheduled for December 2026. **FOCUS 1.5 is not ratified.** Everything about 1.5 here comes from a working draft and can change. Part of the [AI economics redesign](README.md).

## Sources and how far to trust them

Read from the FOCUS site and the FinOps Foundation on 2026-11-07, by documentation review agents (not the authors of this repository):

- The FOCUS 1.5 release-scope page (<https://focus.finops.org/focus-1-5-release-scope/>, dated only "Updated October 2026"; its "in final review" labels may be stale).
- The specification repository's release plan and milestone (<https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec>, milestone page last updated 6 November 2026), the 1.4 introduction (<https://www.finops.org/insights/introducing-focus-1-4/>), and a secondary write-up on 1.5 token cost (<https://www.tokeneconomics.com/projects/what-1-5-does-for-ai-cost-and-what-it-does-not/>).
- The FOCUS 1.4 column pages and changelog. **Most of these pages were truncated and partly summarized by a model**; where a fact depends on such a summary it is marked *(summary)*. Items not found are marked *not found*.

Re-verify everything marked *(draft)* or *(summary)* before relying on it.

## Checked against the unpublished working draft (supplied 2026-11-11)

**[REVIEW REQUIRED]** The owner supplied the FOCUS working-draft specification (a Markdown file whose header reads "Branch: working_draft (Unversioned)" and "This version not for publication") and its machine-readable model (a JSON file marked model version 1.5). The draft's own licence section states CC BY 4.0, so facts below are recorded with attribution and in our own words, and **neither file is stored in this repository**. The owner should confirm that recording details of an unpublished draft here is acceptable before this note is shared outside the team. It is still a working draft: nothing below is ratified.

**What it confirms** (matches the notes above):

- Only **four new columns**, all Conditional: `AllocatedServiceName`, `PrincipalId`, `CredentialId`, `RequesterDetails` (JSON). `AllocatedServiceName` must be null exactly when `AllocatedMethodId` is null, and should match the generator's own `ServiceName`. The draft carries a privacy note that Cost and Usage data can hold personal data, including pseudonymized identity values.
- **AI Model Billing** is a supported feature introduced in 1.5. Tokens ride on `ConsumedQuantity`, `ConsumedUnit`, `PricingQuantity`, `PricingUnit`, `SkuId`, `SkuMeter` and `SkuPriceDetails`; no new columns.
- **`SkuPriceDetails` properties** (recommended, defined with fixed spelling and casing): `ModelDeveloper`, `ModelFamily`, `ModelId`, `ModelVersion`, `TokenDirection` (`Input`, `Output`) and `TokenCacheAction` (`Uncached`, `Read`, `Write`, `Other`). Custom properties must start with `x_`. **No allowed values are defined for the four model properties**, so they are free text and `ModelId` "is not guaranteed to match across service providers". A property is omitted, not guessed, when a price bills several token kinds on one meter.
- **`ConsumedQuantity` must not count a cached token twice**: a cached token counted on a Read or Write row must not also be counted inside another row's quantity. Under that rule, token rows can be summed. That is the draft's rule; this product cannot verify it of a given provider.

**What it corrects or adds:**

- **The SKU Price dataset is a preview in this draft**, "not evaluated for conformance", and may change in the next version, although the release-scope page described it as in final review. The machine-readable model contains only four datasets (Billing Period, Cost and Usage, Contract Commitment, Invoice Detail). Importing SKU Price into the price book stays planned but is not urgent.
- **The draft's AI queries use exact units and filters.** They match `ConsumedUnit = 'Tokens'` (plural: the Unit Format rule gives simple units in the plural, and a unit with a quantity reads "1000 Tokens"), `ServiceCategory = 'AI and Machine Learning'`, `ChargeCategory = 'Usage'`, and, for token quantities, `ChargeClass IS NULL` (corrections excluded). The cache hit rate is cache-read tokens over **all** input token rows; the draft warns it is overstated when a provider emits cache-read rows but none for its other input tokens, and that rows from a single request-and-response meter carry no `TokenDirection` and drop out.
- **The mandatory column list is longer than this importer requires.** The draft makes these Mandatory: `BilledCost`, `BillingAccountId`, `BillingAccountName` (nullable), `BillingCurrency`, `BillingPeriodStart`, `BillingPeriodEnd`, `ChargeCategory`, `ChargeClass` (nullable), `ChargeDescription` (nullable), `ChargePeriodStart`, `ChargePeriodEnd`, `ContractedCost`, `EffectiveCost`, `HostProviderName`, `InvoiceIssuerName`, `ListCost`, `PricingQuantity` (nullable), `PricingUnit` (nullable), `ServiceCategory`, `ServiceName` and `ServiceProviderName`. The importer deliberately requires only the columns it uses plus `ServiceProviderName` for declared 1.4 and 1.5, so it is more lenient than the draft. Reporting a missing mandatory column as a warning (not a rejection) is a sensible follow-up and is **not built**.
- **The machine-readable model is a conformance rule set**: 1,728 rules (1,489 active, 239 removed), 24 operating-model conditions and 42 check functions (regular-expression, decimal, JSON-schema and duplicate checks among them). It could drive a conformance report for imported files. **Not built**; the file's licence and stability as a draft need checking first.
- **Not in 1.5** (from the release-scope page, consistent with the draft): price region scope, reasoning tokens as their own dimension, cache-storage charges, input modality, context-window pricing, priority, standard and batch tiers, provisioned throughput as a commitment, deeper AI subcategories (including agentic AI), a Consumer ID column and scoped requester configuration.

**What this product now does with it.** `GET /v1/cost/ai-tokens` (implemented in `focus/ai.py`) reads imported FOCUS rows and reports tokens, effective cost, effective cost per million tokens, input-to-output ratio and cache hit rate by provider, model, direction and cache action, following the draft's queries and caveats. Rows without a model or direction are counted, a value outside the allowed set is treated as absent and counted, token-like units other than exactly `Tokens` are counted and not summed, corrections are excluded from tokens and shown as their own cost, and an unknown rate is null, never zero. It needs no vendor call and works on any FOCUS export that carries the properties. **Tested on synthetic rows only**: no real provider export that carries these properties has been seen, and none is known to emit them yet.

## Status and schedule

| Item | State |
| --- | --- |
| FOCUS 1.4 | Ratified by the Steering Committee 4 June 2026; the introduction is dated 10 June 2026. 2 new datasets (BillingPeriod, InvoiceDetail), 47 new columns, no incompatible changes. |
| FOCUS 1.5 | Not ratified or announced. Member approval closed 8 October; consistency review 8 to 29 October; IP rights review 2 November to 1 December; working-group approval and ratification 3 December; public announcement "December 2026" (exact date not set). |
| Discrepancy | The milestone page says 1.5 was due 1 October and is overdue, with about 22 open items opened as late as 5 to 6 November. The schedule above may slip. |
| Compatibility | Data that conforms to 1.4 "stays valid as 1.4". No existing column is renamed or removed in 1.5. A 1.4 to 1.5 migration guide was **not yet published**. |
| Validator | The hosted FOCUS Validator offered only 1.2 and 1.3 when read; 1.4 support was promised "later in Q3 2026" and 1.5 support was not shown. **This product cannot use the hosted validator to check 1.4 or 1.5 conformance yet.** |

## What 1.5 changes (working draft)

- **New conditional columns:** `PrincipalId`, `CredentialId`, `RequesterDetails` (identity behind a charge; a JSON array), and `AllocatedServiceName` (on split-cost-allocation rows).
- **New dataset:** SKU Price (list and negotiated prices, effective dates, quantity tiers), conditional on unit pricing; and an "AI Model Billing" supported feature with six worked scenarios.
- **Tightened definitions:** `ListCost`, `ListUnitPrice`, `ContractedCost`, `ContractedUnitPrice`; pricing-currency unit prices aligned with billing-currency ones.
- **Units:** recommended `ConsumedUnit` names `Token`, `Request`, `Character`, `Image`, `Job`, `Message`, `Page`, `Session`.
- **AI conventions inside `SkuPriceDetails`** (recommended, no new columns): `ModelDeveloper`, `ModelFamily`, `ModelId`, `ModelVersion`; and the first properties with fixed values, `TokenDirection` (`Input`, `Output`) and `TokenCacheAction` (`Uncached`, `Read`, `Write`, `Other`). Rules: a price that bills several token kinds on one meter omits the property; a cached token counted on a Read or Write row is not counted again; separately metered reasoning tokens carry `Output`; modality, reasoning effort, cache retention and context window are not values of either property.
- **Currency:** a "consumption currency" lets `PricingCurrency` hold a provider-issued unit such as platform credits; ISO 4217 is for national currencies only.
- **Other:** Service Category descriptions broadened and a Bare Metal subcategory; tag keys preserved exactly as the customer set them; contract commitment duration as number and unit ("1 Year", not "12 Months").
- **Explicitly not in 1.5:** reasoning tokens as their own dimension, standing cache-storage charges, input modality, context-window pricing, batch or priority tiers, provisioned throughput, a Recommendation dataset, and a Consumer ID.

## What it means for this product

| 1.5 item | Effect on this repository | Done now | When 1.5 is ratified |
| --- | --- | --- | --- |
| Identity columns (`PrincipalId`, `CredentialId`, `RequesterDetails`) | They can identify people. Risk R-17. | The importer **drops them by default** and reports which it dropped; `keep_identity_columns` is an explicit choice. The raw file still holds whatever the file contained, so raw retention and redaction need a policy. | Add typed columns only if a privacy review approves. |
| AI token properties | Our `UsageRecord` to FOCUS mapping can follow them. | Mapping table updated: separately metered reasoning tokens carry `Output`. **Names and allowed values confirmed against the supplied draft**, and read by `GET /v1/cost/ai-tokens`. | Re-confirm against the ratified text. |
| Provisioned, batch and priority tiers are not FOCUS concepts | Our `sku` dimension (`api_on_demand`, `api_provisioned`, `subscription`) is product-defined, not a FOCUS field. | Documented as an `x_` extension; not presented as FOCUS. | Revisit if FOCUS adds them. |
| Consumption currency | `PricingCurrency` may not look like an ISO code. | `PricingCurrency` now accepts any non-space token up to 16 characters; `BillingCurrency` stays a three-letter code. | Confirm. **Conflict to resolve:** the 1.4 changelog says 1.4 removed the virtual-currency allowance, while the 1.5 text says the prior text allowed it. |
| SKU Price dataset | A natural source for the price book. The supplied draft marks it **preview**, not evaluated for conformance. | Not built. No provider emitting it was found. | Re-check its status, then plan an importer into `price_entries`. |
| `AllocatedServiceName` | Sits next to provider split allocation. | Preserved as an extension. | Add a typed column. |
| Declared version | Exports may be labelled 1.5 early. | `1.5` is accepted as a declared version; `ServiceProviderName` is required for declared 1.4 and 1.5 (Mandatory in 1.4). | Re-check mandatory columns for 1.5. |
| Validator | Hosted tool lacks 1.4 and 1.5. | Our own importer tests stand in. | Run the validator on sample exports when it supports them. |
| Migration guide | Not published. | Importer is column-name driven, so 1.4 files import unchanged. | Read the guide; adjust. |

## December checklist

When 1.5 is announced, re-verify and update:

1. Ratification and final date; any change to the items marked *(draft)* above.
2. The final column list, requirement levels and **operating model conditions** that now govern Conditional columns.
3. `SkuPriceDetails` property names and values (found in the supplied draft; the four model properties have **no allowed values**), and whether that changed.
4. Whether `PricingCurrency` and consumption currency changed, and the 1.4 versus 1.5 currency conflict.
5. The 1.4 to 1.5 migration guide and Validator support for 1.4 and 1.5.
6. Whether Azure and AWS exports move to 1.4 or 1.5 (Azure's FOCUS export was documented as 1.2-preview, AWS as 1.0 and 1.2 when last read).
7. Update `focus/columns.py`, the data model, this note, and risk R-20.

## Version facts confirmed from the specification history

- `ProviderName` was **replaced by `ServiceProviderName`** (added in 1.3). `ProviderName` and `PublisherName` were deprecated in 1.3 and removed in 1.4. `PublisherName` has no one-to-one successor (`HostProviderName` is only one of several), so it is **not** mapped; it is kept as an extension.
- `ServiceProviderName` is **Mandatory** in 1.4 (and was added in 1.3).
- 1.3 added the provider-calculated split-allocation columns (`AllocatedMethodId`, `AllocatedMethodDetails`, `AllocatedResourceId`, `AllocatedResourceName`, `AllocatedTags`), `ContractApplied`, `HostProviderName`, `ServiceProviderName` and the ContractCommitment dataset. 1.4 added `InvoiceDetailId`, `CommitmentProgramEligibilityDetails` and two datasets, changed `InvoiceId` from Recommended to Conditional, and revised `BilledCost` and `EffectiveCost` requirements.
- 1.0 renamed `UsageQuantity` to `ConsumedQuantity`, `UsageUnit` to `ConsumedUnit` and `Region` to `RegionId`, and removed `ChargeSubcategory`. This importer supports 1.0 and later only.
- Older exports lack newer columns; those columns are simply empty here. The full 1.0 Mandatory list was **not found**.
