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

// ---- economics API (apps/api economics_api.py). Decimals travel as strings: never as floats. ----

export type Basis = "observed" | "estimated" | "assumed";
export type NodeStatus = "ok" | "unknown" | "not_reached" | "infeasible";

export interface Application {
  id: string;
  name: string;
  currency: string;
  owner: string | null;
  lifecycle: "build" | "run" | "retire";
  initial_investment: string | null;
  investment_basis: Basis | null;
  amortization_months: number | null;
}

export interface Assumption {
  key: string;
  version: number;
  value: string | null; // null is "unknown", which is not zero
  unit: string;
  basis: Basis;
  rationale: string;
  author: string;
}

export interface BasisMix {
  observed: string | null;
  estimated: string | null;
  assumed: string | null;
}

export interface FigureNode {
  id: string;
  key: string;
  value: string | null;
  unit: string;
  currency: string | null;
  status: NodeStatus;
  note: string;
  basis: Basis;
  mix: BasisMix;
}

export interface ExplainNode extends FigureNode {
  formula: string;
  formula_version: number;
  label: string;
  source_ref: string | null;
  inputs: ExplainNode[];
}

export interface EvaluateResponse {
  scenario_id: string | null;
  results: Record<string, FigureNode>;
}

export interface CoverageSummary {
  currency: string;
  total_effective: string;
  allocated_effective: string;
  unallocated_effective: string;
  not_yet_allocated_effective: string;
  coverage: string | null;
  by_method: Record<string, string>;
  unallocated_by_reason: Record<string, string>;
  provider_split_lines: number;
}

/** One driver as the scenario endpoint takes it. */
export interface DriverBody {
  value: string | null;
  basis: Basis;
  source?: string;
}
