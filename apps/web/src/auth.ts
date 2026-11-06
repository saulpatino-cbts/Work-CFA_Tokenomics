import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { PublicConfig } from "./types";

/** What the app needs from sign-in. Production uses OIDC; tests and the dev mock use fakes. */
export interface AuthClient {
  /** The access token if signed in, else null. Finishes a pending redirect callback first. */
  token(): Promise<string | null>;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
}

export async function loadConfig(): Promise<PublicConfig> {
  const res = await fetch("/config.json");
  if (!res.ok) throw new Error(`config unavailable (${res.status})`);
  return (await res.json()) as PublicConfig;
}

/** Authorization code + PKCE against the customer's identity provider. No client secret. */
export function oidcAuth(cfg: PublicConfig): AuthClient | null {
  if (!cfg.oidc_issuer || !cfg.oidc_client_id) return null;
  const manager = new UserManager({
    authority: cfg.oidc_issuer,
    client_id: cfg.oidc_client_id,
    redirect_uri: `${window.location.origin}/`,
    post_logout_redirect_uri: `${window.location.origin}/`,
    response_type: "code",
    scope: "openid profile",
    // Tokens live in sessionStorage for the tab only, never localStorage.
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    // Some IdPs need an audience hint to issue a token the API accepts. [VERIFY per IdP]
    extraQueryParams: cfg.oidc_audience ? { audience: cfg.oidc_audience } : undefined,
  });
  return {
    async token() {
      const params = new URLSearchParams(window.location.search);
      if (params.has("code") && params.has("state")) {
        await manager.signinRedirectCallback();
        window.history.replaceState({}, "", window.location.pathname);
      }
      const user = await manager.getUser();
      return user && !user.expired ? user.access_token : null;
    },
    signIn: () => manager.signinRedirect(),
    signOut: () => manager.signoutRedirect(),
  };
}
