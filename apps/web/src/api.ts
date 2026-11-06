import type { Category, SeriesResponse, UsageResponse } from "./types";

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
