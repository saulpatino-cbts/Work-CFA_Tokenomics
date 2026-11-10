import { describe, expect, it } from "vitest";
import type { FigureNode } from "../types";
import { formatFigure, formatMoney, formatPercent, mixShares, trimDecimal } from "./format";

const node = (over: Partial<FigureNode>): FigureNode => ({
  id: "a".repeat(16), key: "k", value: "1", unit: "money", currency: "USD", status: "ok", note: "", basis: "assumed",
  mix: { observed: "0", estimated: "0", assumed: "1" }, ...over,
});

describe("format", () => {
  it("never turns unknown, not-reached or infeasible into a number", () => {
    expect(formatFigure(node({ status: "unknown", value: null }), "money")).toBe("not reported");
    expect(formatFigure(node({ status: "not_reached", value: null }), "months")).toBe("not reached");
    expect(formatFigure(node({ status: "infeasible", value: null }), "money")).toBe("not feasible");
    expect(formatFigure(undefined, "money")).toBe("not reported");
    expect(formatMoney(null, "USD")).toBe("not reported");
    expect(formatPercent(null)).toBe("not reported");
  });
  it("formats money, percent and months", () => {
    expect(formatMoney("6970.0000", "USD")).toBe("$6,970");
    expect(formatMoney("0.005", "USD")).toBe("$0.01");
    expect(formatPercent("2.84153")).toBe("284%");
    expect(formatFigure(node({ value: "4.8387" }), "months")).toBe("4.8 months");
  });
  it("names an unusual currency instead of hiding it", () => {
    expect(formatMoney("5", "CAD")).toContain("CA$");
  });
  it("mix shares are whole numbers that add to exactly 100", () => {
    expect(mixShares({ observed: "0", estimated: "0", assumed: "1" })).toEqual({ observed: 0, estimated: 0, assumed: 100 });
    const s = mixShares({ observed: "1", estimated: "1", assumed: "1" })!;
    expect(s.observed + s.estimated + s.assumed).toBe(100);
    expect(mixShares({ observed: null, estimated: "0", assumed: "1" })).toBeNull();
    expect(mixShares({ observed: "0", estimated: "0", assumed: "0" })).toBeNull();
  });
  it("trims padding zeros as text without touching the digits", () => {
    expect(trimDecimal("10000.000000000000")).toBe("10000");
    expect(trimDecimal("0.800000000000")).toBe("0.8");
    expect(trimDecimal("0.000000000001")).toBe("0.000000000001");
    expect(trimDecimal("-3.50")).toBe("-3.5");
    expect(trimDecimal("100")).toBe("100");
    expect(trimDecimal("1000000.0000000000")).toBe("1000000");
  });
});
