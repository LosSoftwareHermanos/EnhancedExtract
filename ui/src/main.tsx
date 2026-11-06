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
import { QuickExtract, type ShellRequest } from "./QuickExtract";
import { inTauri } from "./engine";
import { mockShellRequest } from "./mock";

async function launch() {
  const root = createRoot(document.getElementById("root")!);
  try {
    const request = inTauri ? await (await import("@tauri-apps/api/core")).invoke<ShellRequest | null>("shell_request") : mockShellRequest();
    root.render(<StrictMode>{request ? <QuickExtract request={request} /> : <App />}</StrictMode>);
  } catch (error) {
    root.render(<main style={{ padding: 32 }} role="alert">Could not start EnhancedExtract: {String(error)}</main>);
  } finally {
    if (inTauri) await (await import("@tauri-apps/api/window")).getCurrentWindow().show();
  }
}
void launch();
