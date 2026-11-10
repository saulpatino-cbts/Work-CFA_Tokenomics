import { useCallback, useEffect, useState } from "react";
import { evaluateScenario, explain, listAssumptions } from "../api";
import type { AuthClient } from "../auth";
import { BasisBadge } from "../components/BasisBadge";
import { ExplainDrawer } from "../components/ExplainDrawer";
import { buildScenario } from "../lib/drivers";
import { formatFigure, mixShares } from "../lib/format";
import { applicationHref } from "../lib/route";
import { errorText } from "../lib/useAsync";
import type { Application, FigureNode } from "../types";

type View =
  | { kind: "loading" }
  | { kind: "missing"; missing: string[] }
  | { kind: "error"; status: number | null; message: string }
  | { kind: "ready"; results: Record<string, FigureNode> };

type As = "money" | "percent" | "months" | "count";

export function Figure({ label, node, as, onExplain }: { label: string; node: FigureNode | undefined; as: As; onExplain: (n: FigureNode, label: string) => void }) {
  return (
    <div className="fig">
      <div className="eyebrow">{label}</div>
      <div className="num">{formatFigure(node, as)}</div>
      {node && (
        <div className="group">
          <BasisBadge basis={node.basis} />
          <button className="sel" onClick={() => onExplain(node, label)} aria-label={`Explain ${label}`}>Explain</button>
        </div>
      )}
    </div>
  );
}

/** Mixed-basis banner: how much of the headline net value rests on assumptions. */
export function AssumptionBanner({ node }: { node: FigureNode | undefined }) {
  const shares = node ? mixShares(node.mix) : null;
  if (!node || !shares) return null;
  return (
    <p className={`notice ${shares.assumed >= 50 ? "warn" : ""}`} role="note">
      <strong>{shares.assumed}% of the net value shown rests on assumptions</strong>, {shares.estimated}% on estimates and {shares.observed}% on observed figures. Treat it as a case to test, not a measured result.
    </p>
  );
}

const numeric = (n: FigureNode | undefined): number | null => (n?.status === "ok" && n.value !== null ? Number(n.value) : null);

/** Bars share one scale across both charts, so the same cost is the same length in each. */
function Bars({ title, rows, currency, max }: { title: string; rows: { label: string; node: FigureNode | undefined }[]; currency: string; max: number }) {
  const nums = rows.map((r) => numeric(r.node));
  return (
    <div role="group" aria-label={title}>
      <div className="eyebrow">{title}</div>
      {rows.map((r, i) => (
        <div className="hbv" key={r.label}>
          <span className="lbl">{r.label}</span>
          <div className="hbt" aria-hidden="true">
            <div className={`hbf ${(nums[i] ?? 0) < 0 ? "neg" : ""}`} style={{ width: `${(Math.abs(nums[i] ?? 0) / max) * 100}%` }} />
          </div>
          <span>{formatFigure(r.node, "money")}</span>
        </div>
      ))}
      <span className="sr-only">Amounts in {currency}.</span>
    </div>
  );
}

export function Economics({ app, auth, canWrite }: { app: Application; auth: AuthClient; canWrite: boolean }) {
  const [view, setView] = useState<View>({ kind: "loading" });
  const [open, setOpen] = useState<{ id: string; title: string } | null>(null);

  const run = useCallback(async () => {
    setView({ kind: "loading" });
    try {
      const token = await auth.token();
      if (!token) throw Object.assign(new Error("signed out"), { status: 401 });
      const built = buildScenario(app.currency, await listAssumptions(token, app.id));
      if (!built.ok) return setView({ kind: "missing", missing: built.missing });
      const res = await evaluateScenario(token, app.id, built.body);
      setView({ kind: "ready", results: res.results });
    } catch (e) {
      setView({ kind: "error", status: (e as { status?: number }).status ?? null, message: e instanceof Error ? e.message : "Request failed" });
    }
  }, [auth, app.id, app.currency]);

  useEffect(() => {
    if (canWrite) void run();
  }, [canWrite, run]);

  const load = useCallback(async () => {
    const token = await auth.token();
    if (!token) throw new Error("Your session has ended. Sign in again.");
    return explain(token, open?.id ?? "");
  }, [auth, open?.id]);

  if (!canWrite)
    return <p className="notice">Calculations are run by users and administrators, because running one stores its calculation record. Your role can read the value model and open stored explanations, but not run a calculation.</p>;
  if (view.kind === "loading") return <p role="status">Calculating…</p>;
  if (view.kind === "error") return <p role="alert">Could not calculate: {errorText(view.status, view.message)} <button className="sel" onClick={() => void run()}>Try again</button></p>;
  if (view.kind === "missing")
    return (
      <div className="block">
        <h2>Not enough to calculate yet</h2>
        <p>These drivers have not been entered. Nothing is assumed in their place.</p>
        <ul>{view.missing.map((m) => <li key={m}>{m}</li>)}</ul>
        <p><a href={applicationHref(app.id, "value")}>Open the value model</a></p>
      </div>
    );

  const r = view.results;
  const explainFn = (n: FigureNode, title: string) => setOpen({ id: n.id, title });
  const F = (label: string, key: string, as: As = "money") => <Figure key={key} label={label} node={r[key]} as={as} onExplain={explainFn} />;
  const hasValue = r["net_value_capacity"] !== undefined;
  const scale = Math.max(1, ...["tca", "business_value_capacity", "business_value_cashable", "net_value_capacity", "net_value_cashable"].map((k) => Math.abs(numeric(r[k]) ?? 0)));

  return (
    <>
      <div className="top">
        <p className="note">Per month, in {app.currency}. Calculated from the value model, so editing an assumption and recalculating changes these figures.</p>
        <button className="sel" onClick={() => void run()}>Recalculate</button>
      </div>
      <AssumptionBanner node={r["net_value_capacity"] ?? r["tca"]} />

      <section className="block" aria-labelledby="e-cost">
        <h2 id="e-cost">What it costs</h2>
        <div className="figs">
          {F("Total cost of application", "tca")}
          {F("Run cost (without build)", "run_cost")}
          {F("AI model cost", "ai_cost")}
          {F("Infrastructure", "infra_cost")}
          {F("Operations", "ops_cost")}
          {F("Build, amortized", "dev_cost")}
        </div>
      </section>

      <section className="block" aria-labelledby="e-unit">
        <h2 id="e-unit">Unit economics</h2>
        <div className="figs">
          {F("Cost per interaction", "cost_per_interaction")}
          {F("Cost per active user", "cost_per_active_user")}
          {F("Cost per transaction", "cost_per_transaction")}
        </div>
      </section>

      <section className="block" aria-labelledby="e-value">
        <h2 id="e-value">What it is worth</h2>
        {!hasValue ? (
          <p className="note">Value is not calculated: the value drivers (hours before and after, loaded rate, realization, cashability) are not all entered. <a href={applicationHref(app.id, "value")}>Add them in the value model.</a></p>
        ) : (
          <>
            <p className="note">Capacity is the time freed. Cashable is the part that turns into money. They are shown side by side and never merged into one headline.</p>
            <div className="two-col">
              {(["capacity", "cashable"] as const).map((t) => (
                <div key={t} className="col">
                  <h3>{t === "capacity" ? "Capacity value" : "Cashable value"}</h3>
                  <div className="figs one">
                    {F("Business value", `business_value_${t}`)}
                    {F("Net value (after total cost)", `net_value_${t}`)}
                    {F("ROI", `roi_${t}`, "percent")}
                    {F("Payback on run cost", `payback_${t}`, "months")}
                  </div>
                  <Bars max={scale} title={`From cost to net value, ${t}`} currency={app.currency} rows={[{ label: "Total cost", node: r["tca"] }, { label: "Business value", node: r[`business_value_${t}`] }, { label: "Net value", node: r[`net_value_${t}`] }]} />
                </div>
              ))}
            </div>
          </>
        )}
      </section>
      {open && <ExplainDrawer title={open.title} load={load} onClose={() => setOpen(null)} />}
    </>
  );
}
