/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs on :8000 (uvicorn onebar.channels.web_server:app). In production the same origin
// serves both, so the app always calls relative /api paths.
// The config is a variable, not a literal, so the `test` block (read by Vitest) is not flagged as an unknown Vite key.
const config = {
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  css: { modules: { localsConvention: "camelCaseOnly" as const } },
  build: { target: "es2022", sourcemap: false },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
};

export default defineConfig(config);
