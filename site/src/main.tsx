import "@fontsource-variable/archivo/wdth.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { prefersReducedMotion } from "./lib/motion";
import "./theme.css";

// Entrance animations hide content until it scrolls into view, so they only
// switch on where IntersectionObserver exists and motion is welcome.
if (typeof IntersectionObserver !== "undefined" && !prefersReducedMotion()) {
  document.documentElement.classList.add("reveal-js");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
