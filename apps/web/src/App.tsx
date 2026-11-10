import { useEffect, useState } from "react";
import { whoami } from "./api";
import { loadConfig, oidcAuth, type AuthClient } from "./auth";
import { parseRoute, type Route } from "./lib/route";
import { ApplicationDetail } from "./pages/ApplicationDetail";
import { Portfolio } from "./pages/Portfolio";
import { Telemetry } from "./pages/Telemetry";

type Session = { kind: "loading" } | { kind: "signed-out" } | { kind: "forbidden" } | { kind: "error"; message: string } | { kind: "ready"; canWrite: boolean };

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

function Shell({ auth }: { auth: AuthClient }) {
  const route = useRoute();
  const [session, setSession] = useState<Session>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const token = await auth.token();
        if (!token) return live && setSession({ kind: "signed-out" });
        const role = await whoami(token);
        if (live) setSession({ kind: "ready", canWrite: role !== "reader" });
      } catch (e) {
        const status = (e as { status?: number }).status;
        if (!live) return;
        if (status === 401) setSession({ kind: "signed-out" });
        else if (status === 403) setSession({ kind: "forbidden" });
        else setSession({ kind: "error", message: e instanceof Error ? e.message : "Request failed" });
      }
    })();
    return () => {
      live = false;
    };
  }, [auth]);

  if (session.kind === "loading") return <div className="state" role="status">Loading…</div>;
  if (session.kind === "signed-out")
    return (
      <div className="state">
        <h1>Sign in</h1>
        <p className="note">Sign-in uses your organisation's identity provider.</p>
        <button className="primary" onClick={() => void auth.signIn()}>Sign in</button>
      </div>
    );
  if (session.kind === "forbidden")
    return <div className="state"><h1>No access yet</h1><p className="note">You are signed in, but no role is mapped to you. Ask a customer administrator.</p></div>;
  if (session.kind === "error")
    return <div className="state" role="alert"><h1>Could not start</h1><p className="note">{session.message}</p></div>;

  return (
    <>
      <nav className="mainnav" aria-label="Main">
        <div className="brand"><div className="logo-ph">logo placeholder</div><div className="eyebrow">CFA Tokenomics <span className="note">(working name)</span></div></div>
        <div className="group">
          <a href="#/" aria-current={route.page === "portfolio" || route.page === "application" ? "page" : undefined}>Applications</a>
          <a href="#/usage" aria-current={route.page === "usage" ? "page" : undefined}>Token usage</a>
          <button className="sel" onClick={() => void auth.signOut()}>Sign out</button>
        </div>
      </nav>
      {route.page === "portfolio" && <Portfolio auth={auth} canWrite={session.canWrite} />}
      {route.page === "usage" && <Telemetry auth={auth} />}
      {route.page === "application" && <ApplicationDetail id={route.id} tab={route.tab} auth={auth} canWrite={session.canWrite} />}
    </>
  );
}

export function App({ auth: injected }: { auth?: AuthClient }) {
  const [auth, setAuth] = useState<AuthClient | null | "none">(injected ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (injected) return;
    loadConfig()
      .then((cfg) => setAuth(oidcAuth(cfg) ?? "none"))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load configuration"));
  }, [injected]);

  return (
    <main className="page">
      <span className="banner">[REVIEW REQUIRED] Brand approval pending · early build, not a release</span>
      {error ? <div className="state" role="alert"><h1>Could not start</h1><p className="note">{error}</p></div>
        : auth === null ? <div className="state" role="status">Loading…</div>
        : auth === "none" ? <div className="state"><h1>Sign-in is not configured</h1><p className="note">An administrator must set the identity provider issuer and client id for this installation.</p></div>
        : <Shell auth={auth} />}
    </main>
  );
}
