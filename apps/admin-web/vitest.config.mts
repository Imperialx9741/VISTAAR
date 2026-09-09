import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Vitest, not Jest (ADR: Admin RBAC UI, 2026-08-28) — this app has no
 * prior frontend test tooling to follow. Vitest is ESM-native and reuses
 * this project's own Vite-compatible React plugin instead of a separate
 * Babel/ts-jest pipeline, and needs no config beyond the "@/*" alias
 * tsconfig.json already declares.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
    },
  },
});
