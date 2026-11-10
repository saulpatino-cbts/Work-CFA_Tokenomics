import type { Application, Assumption, Basis, Category, CoverageSummary, EvaluateResponse, ExplainNode, SeriesResponse, UsageResponse } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type TokenSource = () => Promise<string | null>;

async function get<T>(path: string, params: Record<string, string | string[]>, token: string): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    for (const item of Array.isArray(v) ? v : [v]) url.searchParams.append(k, item);
  }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

export interface Range {
  start: Date;
  end: Date;
}

export function fetchSeries(token: string, r: Range, category: Category): Promise<SeriesResponse> {
  return get("/v1/usage/series", {
    start: r.start.toISOString(),
    end: r.end.toISOString(),
    category,
    bucket: "hour",
    group_by: ["provider", "sku"],
  }, token);
}

export function fetchUsage(token: string, r: Range): Promise<UsageResponse> {
  return get("/v1/usage", { start: r.start.toISOString(), end: r.end.toISOString() }, token);
}

async function send<T>(method: string, path: string, body: unknown, token: string): Promise<T> {
  const res = await fetch(new URL(path, window.location.origin), {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

const seg = encodeURIComponent;

export const listApplications = (token: string) =>
  get<{ applications: Application[] }>("/v1/applications", {}, token).then((r) => r.applications);

export const getApplication = (token: string, id: string) => get<Application>(`/v1/applications/${seg(id)}`, {}, token);

export interface NewApplication {
  name: string;
  currency: string;
  owner?: string;
  lifecycle: "build" | "run" | "retire";
}

export const createApplication = (token: string, body: NewApplication) => send<Application>("POST", "/v1/applications", body, token);

export const listAssumptions = (token: string, id: string) =>
  get<{ assumptions: Assumption[] }>(`/v1/applications/${seg(id)}/assumptions`, {}, token).then((r) => r.assumptions);

export const assumptionHistory = (token: string, id: string, key: string) =>
  get<{ history: Assumption[] }>(`/v1/applications/${seg(id)}/assumptions/${seg(key)}/history`, {}, token).then((r) => r.history);

export interface AssumptionInput {
  value: string | null;
  unit: string;
  basis: Basis;
  rationale: string;
}

export const putAssumption = (token: string, id: string, key: string, body: AssumptionInput) =>
  send<Assumption>("PUT", `/v1/applications/${seg(id)}/assumptions/${seg(key)}`, body, token);

export const evaluateScenario = (token: string, id: string, body: unknown) =>
  send<EvaluateResponse>("POST", `/v1/applications/${seg(id)}/scenarios/evaluate`, body, token);

export const explain = (token: string, nodeId: string) => get<ExplainNode>(`/v1/explain/${seg(nodeId)}`, {}, token);

export const allocationSummary = (token: string) =>
  get<{ summaries: CoverageSummary[] }>("/v1/allocation/summary", {}, token).then((r) => r.summaries);

export const whoami = (token: string) => get<{ role: "admin" | "user" | "reader" }>("/v1/whoami", {}, token).then((r) => r.role);
