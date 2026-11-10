import { useState } from "react";
import { assumptionHistory, listAssumptions, putAssumption } from "../api";
import type { AuthClient } from "../auth";
import { BasisBadge } from "../components/BasisBadge";
import { BASES, GROUP_LABEL, MODEL_NAME, SCALARS, TOKEN_CATEGORIES, modelKey, modelsFrom, parseDecimal, tokenKey, unitOfKey, type Driver } from "../lib/drivers";
import { trimDecimal } from "../lib/format";
import { errorText, useAsync } from "../lib/useAsync";
import type { Application, Assumption, Basis } from "../types";

interface RowProps {
  label: string;
  k: string;
  current: Assumption | undefined;
  app: Application;
  auth: AuthClient;
  canWrite: boolean;
  help?: string;
  onSaved: () => void;
}

/** One assumption: value, basis, rationale. Saving appends a new version; history is never edited. */
function Row({ label, k, current, app, auth, canWrite, help, onSaved }: RowProps) {
  const [value, setValue] = useState(current?.value == null ? "" : trimDecimal(current.value));
  const [unknown, setUnknown] = useState(current !== undefined && current.value === null);
  const [basis, setBasis] = useState<Basis>(current?.basis ?? "assumed");
  const [why, setWhy] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Assumption[] | null>(null);
  const id = `a-${k.replace(/[^a-z0-9]/gi, "-")}`;

  async function save() {
    setProblem(null);
    const parsed = unknown ? null : parseDecimal(value);
    if (!unknown && parsed === null) return setProblem("Enter a number such as 85 or 0.25.");
    if (!why.trim()) return setProblem("Say why: a reason is required for every change.");
    setBusy(true);
    try {
      const token = await auth.token();
      if (!token) throw new Error("Your session has ended. Sign in again.");
      await putAssumption(token, app.id, k, { value: parsed, unit: unitOfKey(k, app.currency), basis, rationale: why.trim() });
      setWhy("");
      setHistory(null);
      onSaved();
    } catch (e) {
      setProblem(errorText((e as { status?: number }).status ?? null, e instanceof Error ? e.message : "Request failed"));
    } finally {
      setBusy(false);
    }
  }

  async function showHistory() {
    if (history) return setHistory(null);
    const token = await auth.token();
    if (token) setHistory(await assumptionHistory(token, app.id, k).catch(() => []));
  }

  return (
    <tr>
      <th scope="row">
        <label htmlFor={`${id}-v`}>{label}</label>
        {help && <div className="note">{help}</div>}
        {current && <div className="note">v{current.version} by {current.author.split("|").pop()}</div>}
      </th>
      <td>
        <input id={`${id}-v`} inputMode="decimal" value={unknown ? "" : value} disabled={!canWrite || unknown} onChange={(e) => setValue(e.target.value)} placeholder={current ? "" : "not set"} aria-describedby={`${id}-u`} />
        <div id={`${id}-u`} className="note">{unitOfKey(k, app.currency)}</div>
        {canWrite && <label className="note"><input type="checkbox" checked={unknown} onChange={(e) => setUnknown(e.target.checked)} /> Unknown</label>}
      </td>
      <td>
        {canWrite ? (
          <select aria-label={`${label}: basis`} value={basis} onChange={(e) => setBasis(e.target.value as Basis)}>
            {BASES.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
          </select>
        ) : current ? <BasisBadge basis={current.basis} /> : "—"}
      </td>
      <td>
        {canWrite ? (
          <>
            <input aria-label={`${label}: reason for this change`} value={why} onChange={(e) => setWhy(e.target.value)} placeholder={current ? `Was: ${current.rationale}` : "Reason (required)"} maxLength={4000} />
            <div className="group">
              <button className="sel" disabled={busy} onClick={() => void save()}>Save</button>
              {current && <button className="sel" aria-expanded={history !== null} onClick={() => void showHistory()}>History</button>}
            </div>
            {problem && <div role="alert" className="note err">{problem}</div>}
          </>
        ) : <span className="note">{current?.rationale ?? ""}</span>}
        {history && (
          <ol className="hist" aria-label={`${label} history`}>
            {history.map((h) => (
              <li key={h.version}>v{h.version}: {h.value === null ? "unknown" : trimDecimal(h.value)} ({h.basis}) · {h.rationale} · {h.author.split("|").pop()}</li>
            ))}
          </ol>
        )}
      </td>
    </tr>
  );
}

export function ValueModel({ app, auth, canWrite }: { app: Application; auth: AuthClient; canWrite: boolean }) {
  const [state, reload] = useAsync(auth, (t) => listAssumptions(t, app.id), [app.id]);
  const [newModel, setNewModel] = useState("");
  const [extra, setExtra] = useState<string[]>([]);

  if (state.kind === "loading") return <p role="status">Loading…</p>;
  if (state.kind === "error") return <p role="alert">Could not load the value model: {errorText(state.status, state.message)}</p>;

  const by = new Map(state.data.map((a) => [a.key, a]));
  const saved = modelsFrom(state.data).map((m) => m.name);
  const names = [...new Set([...saved, ...extra])].sort();
  const cats = TOKEN_CATEGORIES.filter((c) => by.has(tokenKey(c)));
  const priced = cats.length ? cats : (["input", "output"] as const);
  const props = { app, auth, canWrite, onSaved: reload };
  const rowFor = (d: Driver) => <Row key={`${d.key}:${by.get(d.key)?.version ?? 0}`} label={d.label} k={d.key} current={by.get(d.key)} help={d.help} {...props} />;
  const head = (
    <thead>
      <tr><th scope="col">Driver</th><th scope="col">Value</th><th scope="col">Basis</th><th scope="col">Reason</th></tr>
    </thead>
  );

  return (
    <>
      <p className="note">
        Everything on the Economics tab is calculated from the values below. A driver you have not entered stops the calculation; a driver marked Unknown makes the result unknown. Neither is treated as zero.
        Every change needs a reason and is kept as a new version.
        {!canWrite && " Your role can read this model but not change it."}
      </p>

      {(["usage", "cost", "value", "commercial"] as const).map((g) => (
        <section className="block" key={g} aria-labelledby={`g-${g}`}>
          <h2 id={`g-${g}`}>{GROUP_LABEL[g]}</h2>
          {g === "value" && <p className="note">Value is calculated only when all five of the first drivers below are entered: hours before and after, loaded rate, realization and cashability.</p>}
          <table className="vm">
            {head}
            <tbody>
              {g === "usage" && TOKEN_CATEGORIES.map((c) => (
                <Row key={`${c}:${by.get(tokenKey(c))?.version ?? 0}`} label={`Tokens per interaction: ${c.replace("_", " ")}`} k={tokenKey(c)} current={by.get(tokenKey(c))} {...props} />
              ))}
              {SCALARS.filter((d) => d.group === g).map(rowFor)}
            </tbody>
          </table>
        </section>
      ))}

      <section className="block" aria-labelledby="g-models">
        <h2 id="g-models">Models and prices</h2>
        <p className="note">Shares must add up to 1. Prices are per million tokens in {app.currency}; a missing price is never zero. Prices from a price book are estimated, not observed.</p>
        {names.map((n) => (
          <div key={n}>
            <h3>{n}</h3>
            <table className="vm">
              {head}
              <tbody>
                <Row key={`s:${by.get(modelKey(n, "share"))?.version ?? 0}`} label={`${n}: share of token volume`} k={modelKey(n, "share")} current={by.get(modelKey(n, "share"))} {...props} />
                {priced.map((c) => (
                  <Row key={`${c}:${by.get(modelKey(n, `price.${c}`))?.version ?? 0}`} label={`${n}: price, ${c.replace("_", " ")}`} k={modelKey(n, `price.${c}`)} current={by.get(modelKey(n, `price.${c}`))} {...props} />
                ))}
              </tbody>
            </table>
          </div>
        ))}
        {canWrite && (
          <div className="group">
            <label>New model name<input value={newModel} onChange={(e) => setNewModel(e.target.value.toLowerCase())} placeholder="e.g. model-a" /></label>
            <button className="sel" disabled={!MODEL_NAME.test(newModel) || names.includes(newModel)} onClick={() => { setExtra([...extra, newModel]); setNewModel(""); }}>Add model</button>
            {newModel && !MODEL_NAME.test(newModel) && <span className="note">Lowercase letters, digits, - and _, up to 30 characters.</span>}
          </div>
        )}
      </section>
    </>
  );
}
