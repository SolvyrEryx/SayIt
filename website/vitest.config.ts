import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./vitest.setup.tsx"],
    include: ["tests/**/*.test.{ts,tsx}"],
    css: {
      // Don't process the imported globals.css in tests — Vite's PostCSS
      // pipeline rejects Next's postcss.config.mjs format, and tests never
      // assert on processed CSS.
      exclude: [/globals\.css$/],
    },
  },
});
