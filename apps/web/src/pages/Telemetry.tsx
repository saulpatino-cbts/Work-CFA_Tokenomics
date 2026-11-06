import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, fetchSeries, fetchUsage } from "../api";
import type { AuthClient } from "../auth";
import { Heatmap } from "../components/Heatmap";
import { Legend, LineChart } from "../components/LineChart";
import { SERIES_STYLES } from "../components/palette";
import { Sparkline } from "../components/Sparkline";
import { seriesLabel, skuLabel, vendorLabel } from "../lib/labels";
import { formatTokens, hourlyForSource, inWindow, sourcesPresent, totalForSource, weekHeatmap } from "../lib/transform";
import { CATEGORIES, SOURCE_LABEL, type Category, type SeriesResponse, type SourceType, type UsageResponse } from "../types";

type Data = { series: Record<Category, SeriesResponse>; usage: UsageResponse; end: number };
type State = { kind: "loading" } | { kind: "signed-out" } | { kind: "forbidden" } | { kind: "error"; message: string } | { kind: "ready"; data: Data };

const HOUR = 3_600_000;

function ago(iso: string, now: number): string {
  const m = Math.max(0, Math.round((now - Date.parse(iso)) / 60_000));
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
}

const STATUS: Record<string, string> = {
  reconciled: "✓ Reconciled", app_only: "⌂ App only", provider_only: "☁ Provider only",
  app_exceeds_provider: "! App exceeds provider", unknown: "? Unknown",
};

export function Telemetry({ auth }: { auth: AuthClient }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [category, setCategory] = useState<Category>("input");
  const [range, setRange] = useState<24 | 168>(24);
  const [sourcePick, setSourcePick] = useState<SourceType | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const token = await auth.token();
      if (!token) return setState({ kind: "signed-out" });
      const end = Math.ceil(Date.now() / HOUR) * HOUR;
      const week = { start: new Date(end - 168 * HOUR), end: new Date(end) };
      const day = { start: new Date(end - 24 * HOUR), end: new Date(end) };
      const [responses, usage] = await Promise.all([
        Promise.all(CATEGORIES.map((c) => fetchSeries(token, week, c.id))),
        fetchUsage(token, day),
      ]);
      const series = Object.fromEntries(CATEGORIES.map((c, i) => [c.id, responses[i]])) as Record<Category, SeriesResponse>;
      setState({ kind: "ready", data: { series, usage, end } });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return setState({ kind: "signed-out" });
      if (e instanceof ApiError && e.status === 403) return setState({ kind: "forbidden" });
      setState({ kind: "error", message: e instanceof Error ? e.message : "Request failed" });
    }
  }, [auth]);

  useEffect(() => { void load(); }, [load]);

  const ready = state.kind === "ready" ? state.data : null;
  const win = useMemo(() => (ready ? { from: ready.end - range * HOUR, to: ready.end } : null), [ready, range]);
  const week = useMemo(() => (ready ? { from: ready.end - 168 * HOUR, to: ready.end } : null), [ready]);
  const allSeries = useMemo(() => (ready ? CATEGORIES.flatMap((c) => ready.series[c.id].series) : []), [ready]);
  const sources = useMemo(() => sourcesPresent(allSeries), [allSeries]);
  const source: SourceType | null = sourcePick && sources.includes(sourcePick) ? sourcePick : (sources[0] ?? null);

  if (state.kind === "loading") return <div className="state" role="status">Loading usage…</div>;
  if (state.kind === "signed-out")
    return (
      <div className="state">
        <h1>Sign in to see token usage</h1>
        <p className="note">Sign-in uses your organisation's identity provider.</p>
        <button className="primary" onClick={() => void auth.signIn()}>Sign in</button>
      </div>
    );
  if (state.kind === "forbidden")
    return <div className="state"><h1>No access yet</h1><p className="note">You are signed in, but no role or account grant is mapped to you. Ask a customer administrator.</p></div>;
  if (state.kind === "error")
    return <div className="state" role="alert"><h1>Could not load usage</h1><p className="note">{state.message}</p><button className="primary" onClick={() => void load()}>Try again</button></div>;
  if (!ready || !win || !week) return null;
  if (!source)
    return <div className="state"><h1>No usage reported yet</h1><p className="note">Nothing has been collected for the accounts you can see. Unknown is shown as "not reported", never zero.</p></div>;

  const chosen = ready.series[category];
  const shown = chosen.series.filter((s) => s.key.source_type === source && s.points.length > 0);
  const chartSeries = shown.map((s) => ({
    label: seriesLabel(s),
    points: s.points.filter((p) => inWindow(p.t, win)).map((p) => ({ t: Date.parse(p.t), v: p.value })),
  }));
  const providers = new Set(shown.map((s) => s.key.provider));
  const latest = chosen.latest_window_end.filter((l) => l.source_type === source && providers.has(l.provider)).map((l) => Date.parse(l.at));
  const hatchFrom = latest.length ? Math.min(...latest) : null;

  const bySku = shown.map((s) => ({ label: seriesLabel(s), vendor: vendorLabel(s.key.provider), sku: s.key.sku ?? "unknown", total: totalForSource([s], source, win) }));
  const barMax = Math.max(1, ...bySku.map((b) => b.total ?? 0));
  const heat = weekHeatmap(chosen.series, source, week);
  const rows = ready.usage.rows.filter((r) => r.category === category);
  const catLabel = CATEGORIES.find((c) => c.id === category)!.label;

  return (
    <>
      <header className="top">
        <div className="brand">
          <div className="logo-ph">logo placeholder</div>
          <div><div className="eyebrow">CFA Tokenomics <span className="note">(working name)</span></div><h1>Token telemetry</h1></div>
        </div>
        <div className="group" role="group" aria-label="Filters">
          {([24, 168] as const).map((r) => (
            <button key={r} className="sel" aria-pressed={range === r} onClick={() => setRange(r)}>{r === 24 ? "Last 24 h" : "7 d"}</button>
          ))}
          {sources.map((s) => (
            <button key={s} className="sel" aria-pressed={source === s} onClick={() => setSourcePick(s)}>{SOURCE_LABEL[s]}</button>
          ))}
          <button className="sel" aria-pressed={false} onClick={() => void auth.signOut()}>Sign out</button>
        </div>
      </header>

      <section className="cats" aria-label="Token categories">
        {CATEGORIES.map((c) => {
          const total = totalForSource(ready.series[c.id].series, source, win);
          return (
            <div className="block cat" key={c.id}>
              <div className="eyebrow">{c.label}</div>
              <div className="num">{formatTokens(total)}</div>
              <Sparkline values={hourlyForSource(ready.series[c.id].series, source, win).map((p) => p.v)} label={`${c.label} per hour, ${SOURCE_LABEL[source]}`} />
              <div className="note">{SOURCE_LABEL[source]}, summed across vendors</div>
            </div>
          );
        })}
      </section>
      <p className="note">Categories are shown separately and are not summed: providers define cache and reasoning tokens differently. Sources are never added together, since one source can include traffic another also reports. Unknown is "not reported", never zero.</p>

      <section className="main">
        <div className="block">
          <div className="eyebrow">{catLabel} tokens per hour, by vendor and SKU</div>
          <div className="group" role="group" aria-label="Token category" style={{ margin: "8px 0 10px" }}>
            {CATEGORIES.map((c) => (
              <button key={c.id} className="sel" aria-pressed={category === c.id} onClick={() => setCategory(c.id)}>{c.label}</button>
            ))}
          </div>
          {chartSeries.length === 0 ? (
            <p className="note">No {catLabel.toLowerCase()} data from {SOURCE_LABEL[source]} for this period.</p>
          ) : (
            <>
              <LineChart series={chartSeries} from={win.from} to={win.to} hatchFrom={hatchFrom} label={`${catLabel} tokens per hour by vendor and SKU, ${SOURCE_LABEL[source]}`} />
              <Legend labels={chartSeries.map((s) => s.label)} />
            </>
          )}
          <p className="note" style={{ marginTop: 8 }}>Hatched area: hours this source has not reported yet; nothing is drawn there. {chosen.excluded_windows > 0 && `${chosen.excluded_windows} provider windows longer than one hour are not shown. `}{chosen.truncated && "Results were truncated."}</p>
        </div>
        <div className="block">
          <div className="eyebrow">Where {catLabel.toLowerCase()} tokens go: vendor and SKU</div>
          {bySku.map((b, i) => (
            <div className="hb" key={b.label}>
              <div><b>{b.vendor}</b> <span className={`chip ${b.sku === "subscription" ? "dashed" : ""}`}>{skuLabel(b.sku)}</span></div>
              <div className="hbv">
                <div className="hbt"><div className="hbf" style={{ width: `${((b.total ?? 0) / barMax) * 100}%`, background: SERIES_STYLES[i % SERIES_STYLES.length]!.color }} /></div>
                <span>{formatTokens(b.total)}</span>
              </div>
            </div>
          ))}
          <p className="note">SKU shows how usage was bought. "SKU unknown" means the source did not say; it is not guessed.</p>
        </div>
      </section>

      <section className="two">
        <div className="block">
          <div className="eyebrow">When {catLabel.toLowerCase()} tokens are spent (last 7 days, UTC)</div>
          <div style={{ marginTop: 10 }}><Heatmap cells={heat.cells} max={heat.max} label={`${catLabel} tokens by weekday and hour, ${SOURCE_LABEL[source]}`} /></div>
          <p className="note">Dotted cells had no data. They are not zero.</p>
        </div>
        <div className="block navy">
          <div className="eyebrow">Sources and freshness</div>
          <table style={{ marginTop: 8 }}>
            <caption className="sr-only">Latest data per source</caption>
            <thead><tr><th scope="col">Vendor</th><th scope="col">Source</th><th scope="col" className="n">Latest data</th></tr></thead>
            <tbody>
              {chosen.latest_window_end.map((l) => (
                <tr key={`${l.provider}${l.source_type}`}><td><b>{vendorLabel(l.provider)}</b></td><td>{SOURCE_LABEL[l.source_type]}</td><td className="n">{ago(l.at, ready.end)}</td></tr>
              ))}
              {ready.usage.freshness.map((f) => (
                <tr key={`${f.provider}${f.account}`}><td><b>{vendorLabel(f.provider)}</b></td><td>Last collection run</td><td className="n">{ago(f.checkpoint_updated_at, ready.end)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="block">
        <div className="eyebrow">Breakdown, {catLabel.toLowerCase()} tokens, last 24 hours</div>
        <table style={{ marginTop: 8 }}>
          <caption className="sr-only">Reconciliation by vendor, model, SKU and source</caption>
          <thead><tr><th scope="col">Vendor · model</th><th scope="col">SKU</th><th scope="col">Source</th><th scope="col">Reconciliation</th><th scope="col" className="n">Provider</th><th scope="col" className="n">Routed here</th><th scope="col" className="n">Unattributed</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="note">No rows for this category in the last 24 hours.</td></tr>}
            {rows.map((r, i) => (
              <tr key={i}>
                <td><b>{vendorLabel(r.provider)}</b><div className="note">{r.model_id} · {r.account}</div></td>
                <td><span className={`chip ${r.sku === "subscription" ? "dashed" : ""}`}>{skuLabel(r.sku)}</span></td>
                <td>{SOURCE_LABEL[r.source_type]}</td>
                <td><span className="chip">{r.partial ? "~ Partial" : (STATUS[r.status] ?? r.status)}</span></td>
                <td className="n">{formatTokens(r.provider_reported)}</td>
                <td className="n">{r.partial && r.app_observed !== null ? `≥ ${formatTokens(r.app_observed)}` : formatTokens(r.app_observed)}</td>
                <td className="n">{r.partial ? "withheld" : formatTokens(r.unattributed)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
