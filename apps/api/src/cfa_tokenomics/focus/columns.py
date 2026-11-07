"""FOCUS column handling: names, kinds and the few facts this product depends on.

Only facts confirmed from the FOCUS specification are treated as rules. The legacy alias below
is NOT confirmed (VERIFY against the FOCUS 1.0 to 1.2 specifications before relying on it).
"""

MAPPER_VERSION = "focus-csv-1"
FOCUS_TARGET_VERSION = "1.4"
DECLARED_VERSIONS = ("1.0", "1.1", "1.2", "1.3", "1.4", "unknown")

# Confirmed MANDATORY in FOCUS 1.4: BilledCost, EffectiveCost, ListCost, ContractedCost,
# ChargeCategory.
FOCUS_MANDATORY = ("BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory")
# Additionally needed by this product to place a cost line in time and currency.
PRODUCT_REQUIRED = ("ChargePeriodStart", "ChargePeriodEnd", "BillingCurrency")
REQUIRED = FOCUS_MANDATORY + PRODUCT_REQUIRED

# Confirmed values of ChargeCategory in FOCUS 1.4.
CHARGE_CATEGORIES = ("Usage", "Purchase", "Tax", "Credit", "Adjustment")

# Costs and prices are stored as NUMERIC(38, 18); anything finer is rejected, never rounded.
MAX_DECIMAL_PLACES = 18

DECIMAL_REQUIRED = {
    "BilledCost": "billed_cost",
    "EffectiveCost": "effective_cost",
    "ListCost": "list_cost",
    "ContractedCost": "contracted_cost",
}
DECIMAL_OPTIONAL = {
    "ListUnitPrice": "list_unit_price",
    "ContractedUnitPrice": "contracted_unit_price",
    "ConsumedQuantity": "consumed_quantity",
    "PricingQuantity": "pricing_quantity",
    "CommitmentDiscountQuantity": "commitment_discount_quantity",
}
TIMESTAMP_REQUIRED = {
    "ChargePeriodStart": "charge_period_start",
    "ChargePeriodEnd": "charge_period_end",
}
TIMESTAMP_OPTIONAL = {
    "BillingPeriodStart": "billing_period_start",
    "BillingPeriodEnd": "billing_period_end",
}
CURRENCY = {"BillingCurrency": "billing_currency", "PricingCurrency": "pricing_currency"}
JSON_OBJECT = {"Tags": "tags", "SkuPriceDetails": "sku_price_details"}
STRING = {
    "BillingAccountId": "billing_account_id", "BillingAccountName": "billing_account_name",
    "SubAccountId": "sub_account_id", "SubAccountName": "sub_account_name",
    "ChargeCategory": "charge_category", "ChargeClass": "charge_class",
    "ChargeDescription": "charge_description", "ChargeFrequency": "charge_frequency",
    "PricingCategory": "pricing_category", "ConsumedUnit": "consumed_unit",
    "PricingUnit": "pricing_unit",
    "ServiceName": "service_name", "ServiceCategory": "service_category",
    "ServiceSubcategory": "service_subcategory", "ServiceProviderName": "service_provider_name",
    "HostProviderName": "host_provider_name", "InvoiceIssuerName": "invoice_issuer_name",
    "InvoiceId": "invoice_id", "ResourceId": "resource_id", "ResourceName": "resource_name",
    "ResourceType": "resource_type", "RegionId": "region_id", "RegionName": "region_name",
    "AvailabilityZone": "availability_zone", "SkuId": "sku_id", "SkuPriceId": "sku_price_id",
    "SkuMeter": "sku_meter", "CommitmentDiscountId": "commitment_discount_id",
    "CommitmentDiscountName": "commitment_discount_name",
    "CommitmentDiscountCategory": "commitment_discount_category",
    "CommitmentDiscountType": "commitment_discount_type",
    "CommitmentDiscountStatus": "commitment_discount_status",
    "CommitmentDiscountUnit": "commitment_discount_unit",
}  # fmt: skip

# FOCUS 1.0 named the provider column ProviderName. Mapping it to ServiceProviderName is a working
# assumption (VERIFY). The original name is recorded in the row's extensions when it is used.
LEGACY_ALIASES = {"ProviderName": "ServiceProviderName"}

KNOWN = (
    set(DECIMAL_REQUIRED) | set(DECIMAL_OPTIONAL) | set(TIMESTAMP_REQUIRED)
    | set(TIMESTAMP_OPTIONAL)
    | set(CURRENCY) | set(JSON_OBJECT) | set(STRING) | set(LEGACY_ALIASES)
)  # fmt: skip
