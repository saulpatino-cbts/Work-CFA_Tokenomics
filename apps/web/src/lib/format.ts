import type { BasisMix, FigureNode } from "../types";

// Display only. Values stay strings in state and are sent back as strings, so nothing is rounded
// on its way to or from the server. Number() is used here purely to lay out a figure on screen.

export const NOT_REPORTED = "not reported";

export function formatMoney(value: string | null, currency: string | null): string {
  if (value === null) return NOT_REPORTED;
  const n = Number(value);
  if (!Number.isFinite(n)) return NOT_REPORTED;
  const cur = currency && /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  const digits = Math.abs(n) >= 100 ? 0 : 2;
  const text = new Intl.NumberFormat("en-US", { style: "currency", currency: cur, minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  return currency && currency !== cur ? `${text} (${currency})` : text;
}

export function formatPercent(ratio: string | null, places = 0): string {
  if (ratio === null) return NOT_REPORTED;
  const n = Number(ratio);
  return Number.isFinite(n) ? `${(n * 100).toFixed(places)}%` : NOT_REPORTED;
}

export function formatCount(value: string | null): string {
  if (value === null) return NOT_REPORTED;
  const n = Number(value);
  return Number.isFinite(n) ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n) : NOT_REPORTED;
}

/** One figure in words that match its status. Unknown and not-reached are never shown as zero. */
export function formatFigure(n: FigureNode | undefined, as: "money" | "percent" | "months" | "count"): string {
  if (!n) return NOT_REPORTED;
  if (n.status === "unknown") return NOT_REPORTED;
  if (n.status === "not_reached") return "not reached";
  if (n.status === "infeasible") return "not feasible";
  if (as === "money") return formatMoney(n.value, n.currency);
  if (as === "percent") return formatPercent(n.value);
  if (as === "months") return n.value === null ? NOT_REPORTED : `${Number(n.value).toFixed(1)} months`;
  return formatCount(n.value);
}

/** The share of a figure that rests on each basis, as whole percentages that always add to 100. */
export function mixShares(mix: BasisMix): { observed: number; estimated: number; assumed: number } | null {
  const parts = [mix.observed, mix.estimated, mix.assumed].map((p) => (p === null ? NaN : Number(p)));
  if (parts.some((p) => !Number.isFinite(p) || p < 0)) return null;
  const total = parts.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  const raw = parts.map((p) => (p / total) * 100);
  const floors = raw.map(Math.floor);
  let rest = 100 - floors.reduce((a, b) => a + b, 0);
  const order = raw.map((r, i) => ({ i, f: r - Math.floor(r) })).sort((a, b) => b.f - a.f || a.i - b.i);
  for (const { i } of order) {
    if (rest-- <= 0) break;
    floors[i] = (floors[i] ?? 0) + 1;
  }
  return { observed: floors[0] ?? 0, estimated: floors[1] ?? 0, assumed: floors[2] ?? 0 };
}

/** Drop the padding zeros the database adds ("10000.000000" shows as "10000"). Text only, so the exact
 * value is never rounded or re-parsed through a float. */
export function trimDecimal(value: string): string {
  return /^-?\d+\.\d+$/.test(value) ? value.replace(/\.?0+$/, "") : value;
}
