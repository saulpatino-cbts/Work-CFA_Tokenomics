// DEVELOPMENT ONLY. Synthetic data for design review; never bundled into production builds.
// Vendors and SKUs are illustrative and unverified. Values are NOT provider measurements.
import type { AuthClient } from "../auth";
import type { Category, Series, SeriesResponse, SourceType, UsageResponse, UsageRow } from "../types";

export const mockAuth: AuthClient = {
  token: async () => "mock-token",
  signIn: async () => {},
  signOut: async () => {},
};

const HOUR = 3_600_000;
type Def = { provider: string; sku: string; source: SourceType; base: number; lag: number; cats: Category[] };
const ALL: Category[] = ["input", "output", "cache_read", "cache_write", "reasoning"];
const DEFS: Def[] = [
  { provider: "bedrock", sku: "api_on_demand", source: "cloud_telemetry", base: 310_000, lag: 3, cats: ["input", "output", "cache_read", "cache_write"] },
  { provider: "bedrock", sku: "api_provisioned", source: "cloud_telemetry", base: 120_000, lag: 3, cats: ["input", "output"] },
  { provider: "foundry", sku: "api_on_demand", source: "cloud_telemetry", base: 90_000, lag: 6, cats: ["input", "output"] },
  { provider: "vertex_ai", sku: "api_on_demand", source: "cloud_telemetry", base: 60_000, lag: 3, cats: ["input", "output", "cache_read", "reasoning"] },
  { provider: "claude_code", sku: "api_on_demand", source: "vendor_admin_api", base: 210_000, lag: 2, cats: ALL },
  { provider: "openai_codex", sku: "api_on_demand", source: "vendor_admin_api", base: 140_000, lag: 2, cats: ["input", "output", "cache_read", "reasoning"] },
  { provider: "perplexity", sku: "api_on_demand", source: "vendor_admin_api", base: 40_000, lag: 2, cats: ["input", "output"] },
  { provider: "gemini", sku: "api_on_demand", source: "vendor_admin_api", base: 110_000, lag: 2, cats: ["input", "output", "cache_read", "reasoning"] },
  { provider: "bedrock", sku: "unknown", source: "app_routed", base: 70_000, lag: 0, cats: ["input", "output"] },
];

function wave(i: number, base: number, seed: number) {
  const d = new Date(i);
  const hour = d.getUTCHours();
  const weekday = (d.getUTCDay() + 6) % 7 < 5 ? 1 : 0.3;
  const day = 0.2 + Math.exp(-((hour - 14) ** 2) / 30);
  const noise = 0.9 + 0.2 * Math.abs(Math.sin(i / HOUR / 3 + seed));
  return Math.round(base * 0.5 * day * weekday * noise);
}

function seriesFor(category: Category, start: number, end: number): SeriesResponse {
  const scale: Record<Category, number> = { input: 1, output: 0.25, cache_read: 0.6, cache_write: 0.08, reasoning: 0.12 };
  const series: Series[] = [];
  const latest: SeriesResponse["latest_window_end"] = [];
  DEFS.forEach((d, n) => {
    if (!d.cats.includes(category)) return;
    const stop = end - d.lag * HOUR;
    const points = [];
    for (let t = start; t < stop; t += HOUR) points.push({ t: new Date(t).toISOString(), value: wave(t, d.base * scale[category], n), partial: false });
    series.push({ key: { provider: d.provider, sku: d.sku, source_type: d.source }, points });
    if (!latest.some((l) => l.provider === d.provider && l.source_type === d.source))
      latest.push({ provider: d.provider, source_type: d.source, at: new Date(stop).toISOString() });
  });
  return { series, latest_window_end: latest, excluded_windows: 0, truncated: false };
}

function usageFor(end: number): UsageResponse {
  const win = { window_start: new Date(end - 24 * HOUR).toISOString(), window_end: new Date(end).toISOString() };
  const row = (r: Partial<UsageRow>): UsageRow => ({
    provider: "bedrock", account: "account-a", model_id: "model-a", category: "input", ...win, status: "reconciled",
    app_observed: null, provider_reported: null, total: null, unattributed: null, partial: false, aggregate_quality: "reported",
    sku: "api_on_demand", source_type: "cloud_telemetry", ...r,
  });
  return {
    truncated: false,
    rows: [
      row({ app_observed: 1_200_000, provider_reported: 3_100_000, total: 3_100_000, unattributed: 1_900_000 }),
      row({ model_id: "model-b", sku: "api_provisioned", status: "reconciled", partial: true, app_observed: 640_000, provider_reported: 1_250_000, total: 1_250_000 }),
      row({ provider: "foundry", account: "account-b", model_id: "deployment-x", status: "provider_only", provider_reported: 470_000, total: 470_000 }),
      row({ provider: "claude_code", account: "org", model_id: "per-key usage", status: "provider_only", source_type: "vendor_admin_api", provider_reported: 2_400_000, total: 2_400_000 }),
      row({ model_id: "model-c", sku: "unknown", status: "app_only", source_type: "app_routed", aggregate_quality: null, app_observed: 70_000, total: 70_000 }),
    ],
    freshness: [
      { provider: "bedrock", account: "account-a", checkpoint_updated_at: new Date(end - 18 * 60_000).toISOString() },
      { provider: "foundry", account: "account-b", checkpoint_updated_at: new Date(end - 3 * HOUR).toISOString() },
    ],
  };
}

export function installMockApi() {
  const real = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input.toString() : input.url, window.location.origin);
    const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "Content-Type": "application/json" } });
    if (url.pathname === "/v1/usage/series")
      return json(seriesFor(url.searchParams.get("category") as Category, Date.parse(url.searchParams.get("start")!), Date.parse(url.searchParams.get("end")!)));
    if (url.pathname === "/v1/usage") return json(usageFor(Date.parse(url.searchParams.get("end")!)));
    return real(input, init);
  };
}
