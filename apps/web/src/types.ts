export type SourceType = "cloud_telemetry" | "vendor_admin_api" | "app_routed";
export type Category = "input" | "output" | "cache_read" | "cache_write" | "reasoning";

export const CATEGORIES: { id: Category; label: string }[] = [
  { id: "input", label: "Input" },
  { id: "output", label: "Output" },
  { id: "cache_read", label: "Cache read" },
  { id: "cache_write", label: "Cache write" },
  { id: "reasoning", label: "Reasoning" },
];

export const SOURCE_LABEL: Record<SourceType, string> = {
  cloud_telemetry: "Cloud telemetry",
  vendor_admin_api: "Vendor admin API",
  app_routed: "Routed through this app",
};

export const SKU_LABEL: Record<string, string> = {
  api_on_demand: "API · on-demand",
  api_provisioned: "API · provisioned",
  subscription: "Subscription · seats",
  unknown: "SKU unknown",
};

export interface SeriesPoint {
  t: string;
  value: number;
  partial: boolean;
}
export interface SeriesKey {
  provider?: string;
  sku?: string;
  model_id?: string;
  account?: string;
  source_type: SourceType;
}
export interface Series {
  key: SeriesKey;
  points: SeriesPoint[];
}
export interface SeriesResponse {
  series: Series[];
  latest_window_end: { provider: string; source_type: SourceType; at: string }[];
  excluded_windows: number;
  truncated: boolean;
}
export interface UsageRow {
  provider: string;
  account: string;
  model_id: string;
  category: string;
  window_start: string;
  window_end: string;
  status: "app_only" | "provider_only" | "reconciled" | "app_exceeds_provider" | "unknown";
  app_observed: number | null;
  provider_reported: number | null;
  total: number | null;
  unattributed: number | null;
  partial: boolean;
  aggregate_quality: string | null;
  sku: string;
  source_type: SourceType;
}
export interface UsageResponse {
  rows: UsageRow[];
  freshness: { provider: string; account: string; checkpoint_updated_at: string }[];
  truncated: boolean;
}
export interface PublicConfig {
  oidc_issuer: string | null;
  oidc_client_id: string | null;
  oidc_audience: string | null;
}
