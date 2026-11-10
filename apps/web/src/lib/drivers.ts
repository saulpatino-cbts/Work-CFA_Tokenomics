import type { Assumption, Basis, DriverBody } from "../types";

// The value model is a set of assumptions whose keys are the scenario driver names the API takes.
// The editor writes them, the Economics tab reads them back and builds the scenario request, so
// the numbers on screen are exactly the numbers in the editor.

export type Kind = "count" | "ratio" | "money" | "money/hour" | "hours" | "months";
export interface Driver {
  key: string;
  label: string;
  kind: Kind;
  group: "usage" | "cost" | "value" | "commercial";
  required: boolean;
  help?: string;
}

export const TOKEN_CATEGORIES = ["input", "output", "cache_read", "cache_write", "reasoning"] as const;
export const VALUE_KEYS = ["baseline_hours_per_txn", "assisted_hours_per_txn", "loaded_rate", "realization", "cashability"] as const;

export const SCALARS: Driver[] = [
  { key: "users", label: "Users", kind: "count", group: "usage", required: true },
  { key: "adoption", label: "Adoption", kind: "ratio", group: "usage", required: true, help: "Share of users who actively use it, 0 to 1." },
  { key: "interactions_per_user", label: "Interactions per active user per month", kind: "count", group: "usage", required: true },
  { key: "transactions_per_user", label: "Business transactions per user per month", kind: "count", group: "usage", required: true },
  { key: "infra_fixed", label: "Infrastructure, fixed per month", kind: "money", group: "cost", required: true },
  { key: "infra_variable_per_interaction", label: "Infrastructure per interaction", kind: "money", group: "cost", required: false },
  { key: "supporting_api", label: "Supporting APIs per month", kind: "money", group: "cost", required: true },
  { key: "licence", label: "Licences per month", kind: "money", group: "cost", required: true },
  { key: "ops_hours", label: "Operations hours per month", kind: "hours", group: "cost", required: true },
  { key: "ops_rate", label: "Operations rate", kind: "money/hour", group: "cost", required: true },
  { key: "dev_investment", label: "Build investment", kind: "money", group: "cost", required: true },
  { key: "dev_months", label: "Amortization period", kind: "months", group: "cost", required: true },
  { key: "baseline_hours_per_txn", label: "Hours per transaction before", kind: "hours", group: "value", required: false },
  { key: "assisted_hours_per_txn", label: "Hours per transaction with the application", kind: "hours", group: "value", required: false },
  { key: "loaded_rate", label: "Loaded labour rate", kind: "money/hour", group: "value", required: false },
  { key: "realization", label: "Realization", kind: "ratio", group: "value", required: false, help: "Share of the time saved that is actually used." },
  { key: "cashability", label: "Cashability", kind: "ratio", group: "value", required: false, help: "Share of the capacity that turns into money (headcount, contractor or overtime avoided)." },
  { key: "error_value", label: "Value of errors avoided per month", kind: "money", group: "value", required: false },
  { key: "revenue_value", label: "Revenue value per month", kind: "money", group: "value", required: false },
  { key: "avoided_cost", label: "Other avoided cost per month", kind: "money", group: "value", required: false },
  { key: "target_margin", label: "Target margin", kind: "ratio", group: "commercial", required: false },
  { key: "marketplace_fee_rate", label: "Marketplace fee rate", kind: "ratio", group: "commercial", required: false },
  { key: "marketplace_fixed_fee", label: "Marketplace fixed fee", kind: "money", group: "commercial", required: false },
  { key: "price", label: "Price per month", kind: "money", group: "commercial", required: false },
];

export const GROUP_LABEL: Record<Driver["group"], string> = {
  usage: "Usage",
  cost: "Cost",
  value: "Business value",
  commercial: "Pricing and marketplace",
};

export const tokenKey = (cat: string) => `tokens_per_interaction.${cat}`;
export const MODEL_NAME = /^[a-z0-9][a-z0-9_-]{0,29}$/;
export const modelKey = (name: string, part: "share" | `price.${string}`) => `model.${name}.${part}`;

const unitFor = (kind: Kind, currency: string): string => (kind === "money" ? currency : kind === "money/hour" ? `${currency}/hour` : kind);

/** The unit string stored with an assumption. */
export function unitOfKey(key: string, currency: string): string {
  if (key.startsWith("tokens_per_interaction.")) return "tokens";
  if (key.startsWith("model.")) return key.endsWith(".share") ? "ratio" : `${currency}/1M tokens`;
  const d = SCALARS.find((s) => s.key === key);
  return d ? unitFor(d.kind, currency) : "unit";
}

export interface Model {
  name: string;
  keys: Record<string, Assumption>; // "share" or "price.<category>"
}

export function modelsFrom(assumptions: Assumption[]): Model[] {
  const by = new Map<string, Model>();
  for (const a of assumptions) {
    const m = /^model\.([a-z0-9][a-z0-9_-]{0,29})\.(share|price\.[a-z_]+)$/.exec(a.key);
    if (!m) continue;
    const entry = by.get(m[1]!) ?? { name: m[1]!, keys: {} };
    entry.keys[m[2]!] = a;
    by.set(m[1]!, entry);
  }
  return [...by.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export type Built = { ok: true; body: Record<string, unknown> } | { ok: false; missing: string[] };

const toDriver = (a: Assumption): DriverBody => ({ value: a.value, basis: a.basis, source: `assumption ${a.key} v${a.version}` });

/** Build the scenario request from stored assumptions, or say exactly what is missing.
 * A driver that is set to unknown (null) is passed on as unknown, so the result is unknown rather
 * than a guess. A driver that was never entered stops the calculation instead of becoming zero. */
export function buildScenario(currency: string, assumptions: Assumption[]): Built {
  const by = new Map(assumptions.map((a) => [a.key, a]));
  const missing: string[] = [];
  const body: Record<string, unknown> = { currency };
  for (const d of SCALARS) {
    const a = by.get(d.key);
    if (a) body[d.key] = toDriver(a);
    else if (d.required) missing.push(d.label);
  }
  const cats = TOKEN_CATEGORIES.filter((c) => by.has(tokenKey(c)));
  if (cats.length === 0) missing.push("Tokens per interaction (at least one category)");
  body.tokens_per_interaction = Object.fromEntries(cats.map((c) => [c, toDriver(by.get(tokenKey(c))!)]));

  const models = modelsFrom(assumptions);
  if (models.length === 0) missing.push("A model with its share and prices");
  body.models = models.map((m) => {
    const share = m.keys["share"];
    if (!share) missing.push(`Share of ${m.name}`);
    const prices: Record<string, DriverBody> = {};
    for (const c of cats) {
      const p = m.keys[`price.${c}`];
      if (p) prices[c] = toDriver(p);
      else missing.push(`${m.name}: price for ${c.replace("_", " ")} tokens`);
    }
    return { name: m.name, share: share ? toDriver(share) : null, prices };
  });

  const present = VALUE_KEYS.filter((k) => by.has(k));
  if (present.length > 0 && present.length < VALUE_KEYS.length)
    for (const k of VALUE_KEYS)
      if (!by.has(k)) missing.push(`${SCALARS.find((s) => s.key === k)!.label} (needed with the other value drivers)`);

  return missing.length ? { ok: false, missing: [...new Set(missing)] } : { ok: true, body };
}

export const BASES: { id: Basis; label: string }[] = [
  { id: "observed", label: "Observed" },
  { id: "estimated", label: "Estimated" },
  { id: "assumed", label: "Assumed" },
];

/** A decimal typed by a person. Returns the canonical string, or null if it is not an exact decimal. */
export function parseDecimal(text: string): string | null {
  const t = text.trim().replace(/,/g, "");
  return /^-?\d{1,24}(\.\d{1,18})?$/.test(t) ? t : null;
}
