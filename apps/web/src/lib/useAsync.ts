import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api";
import type { AuthClient } from "../auth";

export type Async<T> = { kind: "loading" } | { kind: "error"; status: number | null; message: string } | { kind: "ready"; data: T };

/** Run an authenticated request and keep its state. `reload` runs it again. */
export function useAsync<T>(auth: AuthClient, run: (token: string) => Promise<T>, deps: unknown[]): [Async<T>, () => void] {
  const [state, setState] = useState<Async<T>>({ kind: "loading" });
  const [tick, setTick] = useState(0);
  const fn = useCallback(run, deps);
  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    auth
      .token()
      .then((t) => (t ? fn(t) : Promise.reject(new ApiError(401, "signed out"))))
      .then(
        (data) => live && setState({ kind: "ready", data }),
        (e: unknown) =>
          live &&
          setState({
            kind: "error",
            status: e instanceof ApiError ? e.status : null,
            message: e instanceof Error ? e.message : "Request failed",
          }),
      );
    return () => {
      live = false;
    };
  }, [auth, fn, tick]);
  return [state, () => setTick((n) => n + 1)];
}

export function errorText(status: number | null, message: string): string {
  if (status === 401) return "Your session has ended. Sign in again.";
  if (status === 403) return "Your role does not allow this.";
  if (status === 404) return "That record was not found.";
  if (status === 503) return "The installation has no tenant configured yet. An administrator must set it.";
  try {
    const detail = (JSON.parse(message) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`).join("; ");
  } catch {
    /* not JSON */
  }
  return message || "Request failed";
}
