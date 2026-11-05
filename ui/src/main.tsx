import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts ship with the app (no network). Oxanium: squared and chamfered like the Σ logo, with
// equal-width digits, for titles and every figure. Bai Jamjuree: a clean technical text face.
import "@fontsource/oxanium/500.css";
import "@fontsource/oxanium/600.css";
import "@fontsource/oxanium/700.css";
import "@fontsource/bai-jamjuree/400.css";
import "@fontsource/bai-jamjuree/500.css";
import "@fontsource/bai-jamjuree/600.css";
import "./styles.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
