import { describe, expect, it } from "vitest";
import type { Assumption, Basis } from "../types";
import { buildScenario, modelKey, modelsFrom, parseDecimal, tokenKey, unitOfKey } from "./drivers";

const a = (key: string, value: string | null, basis: Basis = "assumed"): Assumption => ({ key, version: 2, value, unit: "u", basis, rationale: "r", author: "https://idp|ann" });

const REQUIRED = ["users", "adoption", "interactions_per_user", "transactions_per_user", "infra_fixed", "supporting_api", "licence", "ops_hours", "ops_rate", "dev_investment", "dev_months"];
const full = (): Assumption[] => [
  ...REQUIRED.map((k) => a(k, "1")),
  a(tokenKey("input"), "10000"), a(tokenKey("output"), "2500"),
  a(modelKey("m", "share"), "1"), a(modelKey("m", "price.input"), "3", "estimated"), a(modelKey("m", "price.output"), "15", "estimated"),
];

describe("buildScenario", () => {
  it("builds the request the API takes, carrying basis and where each value came from", () => {
    const r = buildScenario("USD", full());
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.body.currency).toBe("USD");
    expect(r.body.users).toEqual({ value: "1", basis: "assumed", source: "assumption users v2" });
    expect(Object.keys(r.body.tokens_per_interaction as object)).toEqual(["input", "output"]);
    const models = r.body.models as { name: string; share: unknown; prices: Record<string, { basis: string }> }[];
    expect(models).toHaveLength(1);
    expect(models[0]!.prices.input!.basis).toBe("estimated");
    expect(r.body.baseline_hours_per_txn).toBeUndefined(); // not entered is not sent, never zero
  });
  it("names what is missing instead of guessing", () => {
    const r = buildScenario("USD", full().filter((x) => x.key !== "licence" && x.key !== modelKey("m", "price.output")));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.missing).toContain("Licences per month");
    expect(r.missing).toContain("m: price for output tokens");
  });
  it("needs a model, a token category and every value driver once one is entered", () => {
    expect(buildScenario("USD", REQUIRED.map((k) => a(k, "1")))).toMatchObject({ ok: false });
    const partial = [...full(), a("loaded_rate", "85")];
    const r = buildScenario("USD", partial);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.missing.some((m) => m.startsWith("Hours per transaction before"))).toBe(true);
  });
  it("passes an unknown driver on as unknown (null), not zero", () => {
    const r = buildScenario("USD", full().map((x) => (x.key === "licence" ? a("licence", null) : x)));
    expect(r.ok).toBe(true);
    if (r.ok) expect((r.body.licence as { value: unknown }).value).toBeNull();
  });
  it("groups model keys and ignores malformed ones", () => {
    const ms = modelsFrom([a("model.b.share", "1"), a("model.a.price.input", "3"), a("model.Bad Name.share", "1"), a("users", "1")]);
    expect(ms.map((m) => m.name)).toEqual(["a", "b"]);
  });
  it("derives the stored unit from the key and currency", () => {
    expect(unitOfKey("licence", "EUR")).toBe("EUR");
    expect(unitOfKey("ops_rate", "EUR")).toBe("EUR/hour");
    expect(unitOfKey(modelKey("m", "price.input"), "EUR")).toBe("EUR/1M tokens");
    expect(unitOfKey(tokenKey("input"), "EUR")).toBe("tokens");
  });
});

describe("parseDecimal", () => {
  it("accepts exact decimals and refuses everything else", () => {
    expect(parseDecimal(" 1,250.50 ")).toBe("1250.50");
    expect(parseDecimal("-3")).toBe("-3");
    for (const bad of ["", "abc", "1e3", "0x10", "1.2.3", "NaN", "1.1234567890123456789"]) expect(parseDecimal(bad)).toBeNull();
  });
});
