import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API is expected on :8080; in production it serves this build itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/v1": "http://localhost:8080", "/config.json": "http://localhost:8080" } },
  test: { environment: "node" },
});
