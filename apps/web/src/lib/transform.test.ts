import { describe, expect, it } from "vitest";
import type { Series } from "../types";
import { formatTokens, hourlyForSource, niceMax, sourcesPresent, totalForSource, weekHeatmap } from "./transform";

const pt = (t: string, value: number) => ({ t, value, partial: false });
const W = { from: Date.parse("2026-01-05T00:00:00Z"), to: Date.parse("2026-01-06T00:00:00Z") };
const mk = (source: Series["key"]["source_type"], points: Series["points"], provider = "bedrock"): Series => ({
  key: { provider, source_type: source },
  points,
});

describe("formatTokens", () => {
  it("never turns unknown into zero", () => {
    expect(formatTokens(null)).toBe("not reported");
    expect(formatTokens(undefined)).toBe("not reported");
    expect(formatTokens(0)).toBe("0");
  });
  it("compacts", () => {
    expect(formatTokens(1_234_567)).toBe("1.23M");
    expect(formatTokens(12_300)).toBe("12.3k");
    expect(formatTokens(999)).toBe("999");
  });
});

describe("totalForSource", () => {
  it("sums within one source across vendors", () => {
    const s = [
      mk("cloud_telemetry", [pt("2026-01-05T01:00:00Z", 10)], "bedrock"),
      mk("cloud_telemetry", [pt("2026-01-05T02:00:00Z", 5)], "foundry"),
    ];
    expect(totalForSource(s, "cloud_telemetry", W)).toBe(15);
  });
  it("never adds different sources", () => {
    const s = [
      mk("cloud_telemetry", [pt("2026-01-05T01:00:00Z", 10)]),
      mk("vendor_admin_api", [pt("2026-01-05T01:00:00Z", 12)]),
    ];
    expect(totalForSource(s, "cloud_telemetry", W)).toBe(10);
    expect(totalForSource(s, "vendor_admin_api", W)).toBe(12);
  });
  it("returns null, not zero, when a source reported nothing in the window", () => {
    expect(totalForSource([mk("cloud_telemetry", [pt("2026-01-04T01:00:00Z", 10)])], "cloud_telemetry", W)).toBeNull();
    expect(totalForSource([], "app_routed", W)).toBeNull();
  });
});

describe("hourlyForSource", () => {
  it("skips missing hours and sorts", () => {
    const s = [mk("cloud_telemetry", [pt("2026-01-05T03:00:00Z", 3), pt("2026-01-05T01:00:00Z", 1)])];
    expect(hourlyForSource(s, "cloud_telemetry", W).map((p) => p.v)).toEqual([1, 3]);
  });
});

describe("weekHeatmap", () => {
  it("maps Monday 14:00 UTC and leaves empty cells null", () => {
    const s = [mk("cloud_telemetry", [pt("2026-01-05T14:00:00Z", 8)])]; // 2026-01-05 is a Monday
    const h = weekHeatmap(s, "cloud_telemetry", W);
    expect(h.cells[0]?.[14]).toBe(8);
    expect(h.cells[0]?.[13]).toBeNull();
    expect(h.max).toBe(8);
  });
  it("ignores other sources", () => {
    const s = [mk("vendor_admin_api", [pt("2026-01-05T14:00:00Z", 8)])];
    expect(weekHeatmap(s, "cloud_telemetry", W).max).toBe(0);
  });
});

describe("sourcesPresent / niceMax", () => {
  it("lists only sources with points, in a stable order", () => {
    const s = [mk("app_routed", [pt("2026-01-05T01:00:00Z", 1)]), mk("cloud_telemetry", []), mk("vendor_admin_api", [pt("2026-01-05T01:00:00Z", 1)])];
    expect(sourcesPresent(s)).toEqual(["vendor_admin_api", "app_routed"]);
  });
  it("rounds an axis maximum up", () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(310)).toBe(500);
    expect(niceMax(1000)).toBe(1000);
  });
});
