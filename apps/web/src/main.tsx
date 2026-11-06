import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

async function start() {
  let auth;
  // Development-only mock data for design review. Dropped from production builds.
  if (import.meta.env.DEV && new URLSearchParams(window.location.search).has("mock")) {
    const mock = await import("./dev/mock");
    mock.installMockApi();
    auth = mock.mockAuth;
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App auth={auth} />
    </StrictMode>,
  );
}
void start();
