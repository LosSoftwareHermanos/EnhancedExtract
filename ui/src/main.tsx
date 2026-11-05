import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts ship with the app (no network): Public Sans for text, JetBrains Mono for figures.
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "./styles.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
