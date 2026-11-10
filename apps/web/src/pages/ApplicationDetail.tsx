import type { AuthClient } from "../auth";
import { applicationHref, TABS, type Tab } from "../lib/route";
import { errorText, useAsync } from "../lib/useAsync";
import { getApplication } from "../api";
import { CostView } from "./CostView";
import { Economics } from "./Economics";
import { Telemetry } from "./Telemetry";
import { ValueModel } from "./ValueModel";

export function ApplicationDetail({ id, tab, auth, canWrite }: { id: string; tab: Tab; auth: AuthClient; canWrite: boolean }) {
  const [state] = useAsync(auth, (t) => getApplication(t, id), [id]);
  if (state.kind === "loading") return <p role="status">Loading…</p>;
  if (state.kind === "error") return <div className="state" role="alert"><h1>Could not open the application</h1><p className="note">{errorText(state.status, state.message)}</p><a href="#/">Back to the portfolio</a></div>;
  const app = state.data;
  return (
    <>
      <header className="top">
        <div>
          <div className="eyebrow"><a href="#/">Portfolio</a> / {app.currency} · {app.lifecycle}</div>
          <h1>{app.name}</h1>
        </div>
      </header>
      <nav aria-label="Application sections" className="tabs">
        {TABS.map((t) => (
          <a key={t.id} href={applicationHref(app.id, t.id)} aria-current={t.id === tab ? "page" : undefined}>{t.label}</a>
        ))}
      </nav>
      {tab === "economics" && <Economics app={app} auth={auth} canWrite={canWrite} />}
      {tab === "value" && <ValueModel app={app} auth={auth} canWrite={canWrite} />}
      {tab === "cost" && <CostView auth={auth} />}
      {tab === "usage" && <Telemetry auth={auth} embedded />}
    </>
  );
}
