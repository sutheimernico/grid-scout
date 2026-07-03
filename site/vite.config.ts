import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base matches the GitHub Pages project path: sutheimernico.github.io/grid-scout/
export default defineConfig({
  plugins: [react()],
  base: "/grid-scout/",
});
