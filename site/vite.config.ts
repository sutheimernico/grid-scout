/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base matches the GitHub Pages project path: sutheimernico.github.io/grid-scout/
export default defineConfig({
  plugins: [react()],
  base: "/grid-scout/",
  test: {
    // component tests need a DOM; the chart-math tests do not care
    environment: "jsdom",
    globals: false,
  },
});
