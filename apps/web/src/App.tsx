import { useEffect, useState } from "react";
import { loadConfig, oidcAuth, type AuthClient } from "./auth";
import { Telemetry } from "./pages/Telemetry";

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
        : <Telemetry auth={auth} />}
    </main>
  );
}
