import { useState } from "react";
import { allocationSummary, createApplication, listApplications } from "../api";
import type { AuthClient } from "../auth";
import { formatMoney, formatPercent } from "../lib/format";
import { applicationHref } from "../lib/route";
import { errorText, useAsync } from "../lib/useAsync";

export function Portfolio({ auth, canWrite }: { auth: AuthClient; canWrite: boolean }) {
  const [apps, reloadApps] = useAsync(auth, listApplications, []);
  const [cover] = useAsync(auth, allocationSummary, []);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [owner, setOwner] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setProblem(null);
    setBusy(true);
    try {
      const token = await auth.token();
      if (!token) throw new Error("Your session has ended. Sign in again.");
      await createApplication(token, { name: name.trim(), currency: currency.trim(), owner: owner.trim() || undefined, lifecycle: "run" });
      setName("");
      setOwner("");
      reloadApps();
    } catch (err) {
      setProblem(err instanceof Error ? errorText((err as { status?: number }).status ?? null, err.message) : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="top">
        <div>
          <div className="eyebrow">Portfolio</div>
          <h1>AI applications</h1>
        </div>
      </header>

      <section className="block" aria-labelledby="apps-h">
        <h2 id="apps-h">Applications</h2>
        {apps.kind === "loading" && <p role="status">Loading…</p>}
        {apps.kind === "error" && <p role="alert">Could not load applications: {errorText(apps.status, apps.message)}</p>}
        {apps.kind === "ready" && apps.data.length === 0 && (
          <p className="note">No applications yet. {canWrite ? "Add the first one below." : "Ask a user or administrator to add one."}</p>
        )}
        {apps.kind === "ready" && apps.data.length > 0 && (
          <table>
            <thead>
              <tr><th scope="col">Application</th><th scope="col">Owner</th><th scope="col">Lifecycle</th><th scope="col">Currency</th><th scope="col" className="n">Build investment</th></tr>
            </thead>
            <tbody>
              {apps.data.map((a) => (
                <tr key={a.id}>
                  <th scope="row"><a href={applicationHref(a.id)}>{a.name}</a></th>
                  <td>{a.owner ?? "—"}</td>
                  <td>{a.lifecycle}</td>
                  <td>{a.currency}</td>
                  <td className="n">{a.initial_investment === null ? "not set" : formatMoney(a.initial_investment, a.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="note">Cost, value and ROI are calculated per application from its value model; open an application to see them. There is no portfolio-wide rollup yet.</p>
      </section>

      {canWrite && (
        <form className="block form" onSubmit={(e) => void add(e)} aria-labelledby="new-h">
          <h2 id="new-h">Add an application</h2>
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} required maxLength={256} /></label>
          <label>Owner (optional)<input value={owner} onChange={(e) => setOwner(e.target.value)} maxLength={256} /></label>
          <label>Currency<input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} required pattern="[A-Za-z]{3}" maxLength={3} aria-describedby="cur-h" /></label>
          <p id="cur-h" className="note">Three letters, for example USD. One currency per application; amounts in different currencies are never added.</p>
          <div><button className="primary" disabled={busy || !name.trim()}>Add application</button></div>
          {problem && <p role="alert">{problem}</p>}
        </form>
      )}

      <section className="block" aria-labelledby="cov-h">
        <h2 id="cov-h">Cost allocation coverage</h2>
        <p className="note">Across everything imported, in each currency separately.</p>
        {cover.kind === "loading" && <p role="status">Loading…</p>}
        {cover.kind === "error" && <p role="alert">Could not load coverage: {errorText(cover.status, cover.message)}</p>}
        {cover.kind === "ready" && cover.data.length === 0 && <p className="note">No cost has been imported yet.</p>}
        {cover.kind === "ready" &&
          cover.data.map((s) => (
            <p key={s.currency}>
              <strong>{s.currency}</strong>: {formatPercent(s.coverage)} of effective cost is allocated to an application ({formatMoney(s.allocated_effective, s.currency)} of {formatMoney(s.total_effective, s.currency)}).
            </p>
          ))}
      </section>
    </>
  );
}
