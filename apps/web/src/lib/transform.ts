import type { Series, SourceType } from "../types";

/** Compact token counts. Unknown is "not reported", never zero. */
export function formatTokens(n: number | null | undefined): string {
  if (n === null || n === undefined) return "not reported";
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(a >= 1e5 ? 0 : 1)}k`;
  return String(Math.round(n));
}

const ms = (t: string) => Date.parse(t);

export interface Window {
  from: number;
  to: number;
}

export function inWindow(t: string, w: Window): boolean {
  const x = ms(t);
  return x >= w.from && x < w.to;
}

/**
 * Sum of one source's series inside a window, or null if that source reported nothing.
 * Series from different sources are NEVER added: the same traffic can appear in more than one.
 */
export function totalForSource(series: Series[], source: SourceType, w: Window): number | null {
  let total: number | null = null;
  for (const s of series) {
    if (s.key.source_type !== source) continue;
    for (const p of s.points) {
      if (inWindow(p.t, w)) total = (total ?? 0) + p.value;
    }
  }
  return total;
}

/** Hourly values for one source in a window, for a sparkline. Missing hours are skipped. */
export function hourlyForSource(series: Series[], source: SourceType, w: Window): { t: number; v: number }[] {
  const byHour = new Map<number, number>();
  for (const s of series) {
    if (s.key.source_type !== source) continue;
    for (const p of s.points) {
      if (inWindow(p.t, w)) byHour.set(ms(p.t), (byHour.get(ms(p.t)) ?? 0) + p.value);
    }
  }
  return [...byHour.entries()].sort((a, b) => a[0] - b[0]).map(([t, v]) => ({ t, v }));
}

/** Weekday (Mon=0) by hour (UTC) matrix for one source. null cells had no data. */
export function weekHeatmap(series: Series[], source: SourceType, w: Window) {
  const cells: (number | null)[][] = Array.from({ length: 7 }, () => Array(24).fill(null));
  for (const s of series) {
    if (s.key.source_type !== source) continue;
    for (const p of s.points) {
      if (!inWindow(p.t, w)) continue;
      const d = new Date(p.t);
      const row = (d.getUTCDay() + 6) % 7;
      const col = d.getUTCHours();
      const r = cells[row] as (number | null)[];
      r[col] = (r[col] ?? 0) + p.value;
    }
  }
  const max = Math.max(0, ...cells.flat().map((x) => x ?? 0));
  return { cells, max };
}

/** Sources that actually have data, in a stable preferred order. */
export function sourcesPresent(series: Series[]): SourceType[] {
  const order: SourceType[] = ["cloud_telemetry", "vendor_admin_api", "app_routed"];
  const have = new Set(series.filter((s) => s.points.length > 0).map((s) => s.key.source_type));
  return order.filter((s) => have.has(s));
}

export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const f = v / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
