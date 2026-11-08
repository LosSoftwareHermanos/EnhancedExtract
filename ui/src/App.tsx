import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { inTauri, jobsList, pickArchive, systemCheck, type JobSnap, type SystemCheck } from "./engine";
import { useAction, usePoll, useStored } from "./hooks";
import { isArchive, isIso } from "./format";
import { Boot, Decode, FxContext } from "./fx/motion";
import { Icon, WindowControls } from "./components/ui";
import { installSounds, play, preload } from "./sound";
import { Library } from "./screens/Library";
import { RarSetup } from "./screens/RarSetup";
import { RarRunning } from "./screens/RarRunning";
import { IsoSetup } from "./screens/IsoSetup";
import { IsoRunning } from "./screens/IsoRunning";
import { Jobs } from "./screens/Jobs";
import logo from "./assets/logo-64.png";
import wordmark from "./assets/wordmark.png";

export type Route =
  | { name: "library" }
  | { name: "rar"; path?: string }
  | { name: "rarJob"; id: string }
  | { name: "iso"; path?: string }
  | { name: "isoJob"; id: string }
  | { name: "jobs"; id?: string };

interface Ctx {
  route: Route;
  nav: (r: Route) => void;
  jobs: JobSnap[] | null;
  refreshJobs: () => void;
  system: SystemCheck | null;
  recheck: () => Promise<void>;
  announce: (msg: string) => void;
  openPath: (path: string) => void;
  fx: boolean;
  setFx: (on: boolean) => void;
}
const AppCtx = createContext<Ctx>(null!);
export const useApp = () => useContext(AppCtx);

/** Where a job's screen lives: RAR jobs on the extract screen, ISO jobs on the install screen. */
export const jobRoute = (j: JobSnap): Route => ((j.argv?.[0] ?? j.command.split(" ")[0]) === "iso" ? { name: "isoJob", id: j.id } : { name: "rarJob", id: j.id });

export function App() {
  const [route, setRoute] = useState<Route>(previewRoute);
  const [live, setLive] = useState("");
  const [dragging, setDragging] = useState(false);
  const jobs = usePoll(() => jobsList(30), 4000);
  const sys = usePoll(systemCheck, 600000);
  const [fx, setFx] = useStored("ee.fx", true);
  // The start-up sequence plays once per launch, and never with reduced motion or effects off.
  const [booting, setBooting] = useState(() => {
    try { return fx && !sessionStorage.getItem("ee.booted") && !matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
  });
  const bootDone = useCallback(() => { setBooting(false); try { sessionStorage.setItem("ee.booted", "1"); } catch { /* private mode */ } }, []);

  const nav = useCallback((r: Route) => { setRoute(r); document.querySelector<HTMLElement>(".canvas")?.scrollTo(0, 0); }, []);
  const announce = useCallback((m: string) => { setLive(""); setTimeout(() => setLive(m), 50); }, []);
  const openPath = useCallback((p: string) => {
    if (isIso(p)) nav({ name: "iso", path: p });
    else if (isArchive(p)) nav({ name: "rar", path: p });
    else announce("Drop an archive (.rar, .zip, .7z, .tar.gz and more) or an .iso file.");
  }, [nav, announce]);

  useEffect(() => { void preload(); return installSounds(); }, []);

  // Explorer "Open with EnhancedExtract" launches with --open <file>: go straight to its screen.
  useEffect(() => {
    if (!inTauri) return;
    void import("@tauri-apps/api/core").then(({ invoke }) => invoke<string | null>("open_request")).then((p) => { if (p) openPath(p); }).catch(() => {});
  }, [openPath]);

  // A job that finishes while you look elsewhere is announced once.
  const [seen, setSeen] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!jobs.data) return;
    const next: Record<string, string> = {};
    for (const j of jobs.data) {
      next[j.id] = j.state;
      if (seen[j.id] === "running" && j.state !== "running") announce(`${j.state === "done" ? "Finished" : "Failed"}: ${j.command}`);
    }
    setSeen(next);
  }, [jobs.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Drag and drop from Explorer: an archive or .iso opens its set-up screen.
  useEffect(() => {
    if (!inTauri) return;
    let unlisten: (() => void) | undefined;
    import("@tauri-apps/api/webview").then(({ getCurrentWebview }) =>
      getCurrentWebview().onDragDropEvent((e) => {
        if (e.payload.type === "over" || e.payload.type === "enter") setDragging(true);
        else setDragging(false);
        if (e.payload.type === "drop" && e.payload.paths[0]) openPath(e.payload.paths[0]);
      }).then((u) => (unlisten = u)));
    return () => unlisten?.();
  }, [openPath]);

  // Ctrl+O opens a set from anywhere.
  useEffect(() => {
    const onKey = async (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); const p = await pickArchive(); if (p) openPath(p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPath]);

  const ctx: Ctx = { route, nav, jobs: jobs.data, refreshJobs: jobs.refresh, system: sys.data, recheck: sys.refresh, announce, openPath, fx, setFx };
  const running = (jobs.data ?? []).filter((j) => j.state === "running").length;

  return (
    <AppCtx.Provider value={ctx}>
      <FxContext.Provider value={fx}>
        <div className={`app${fx ? "" : " fx-off"}`}>
          <Rail running={running} />
          <TitleBar />
          {/* keyed by screen, so each screen change replays the entrance */}
          <main className="canvas" id="main" key={JSON.stringify(route)}>{screen(route)}</main>
        </div>
        <div className="sr-only" aria-live="polite">{live}</div>
        {dragging && <div className="drop"><img src={logo} alt="" style={{ width: 64, height: 64 }} />Drop an archive or an .iso to set it up</div>}
        {booting && <Boot onDone={bootDone} />}
      </FxContext.Provider>
    </AppCtx.Provider>
  );
}

/** Browser preview only (mock engine): open a screen straight from the URL, e.g. #rar or #isoJob. */
function previewRoute(): Route {
  if (inTauri) return { name: "library" };
  const h = location.hash.slice(1);
  const routes: Record<string, Route> = {
    rar: { name: "rar", path: "D:\\Downloads\\Ashen.Tide.v1.4.2.part01.rar" }, rarJob: { name: "rarJob", id: "3f9a" },
    iso: { name: "iso", path: "E:\\Downloads\\Vigil.of.Ostra.iso" }, isoJob: { name: "isoJob", id: "c9f3" }, jobs: { name: "jobs" },
  };
  return routes[h] ?? { name: "library" };
}

function screen(r: Route): ReactNode {
  switch (r.name) {
    case "library": return <Library />;
    case "rar": return <RarSetup key={r.path} path={r.path} />;
    case "rarJob": return <RarRunning key={r.id} id={r.id} />;
    case "iso": return <IsoSetup key={r.path} path={r.path} />;
    case "isoJob": return <IsoRunning key={r.id} id={r.id} />;
    case "jobs": return <Jobs initial={r.id} />;
  }
}

const SECTION: Record<Route["name"], string> = { library: "library", rar: "extract", rarJob: "jobs", iso: "disc", isoJob: "jobs", jobs: "jobs" };

function Rail({ running }: { running: number }) {
  const { route, nav, system, fx, setFx } = useApp();
  const here = SECTION[route.name];
  const order = ["library", "extract", "disc", "jobs"];
  const idx = order.indexOf(here);
  // Changing screen plays one tab sound (forceField_001) for every screen.
  const item = (id: string, label: string, to: Route, badge: "" | "now" | "bad" = "") => (
    <button className="ri" aria-current={here === id ? "page" : undefined} aria-label={label} onClick={() => nav(to)}
      data-sound={here === id ? "none" : "tab"}>
      <Icon name={id} />{badge && <span className={`badge ${badge === "bad" ? "bad" : ""}`} aria-hidden="true" />}<span className="tip">{label}</span>
    </button>
  );
  const sysBad = system && (!system.unrar || !system.sevenzip || !system.winfsp || !system.fusepy);
  const [sysOpen, setSysOpen] = useState(false);
  return (
    <nav className="rail" aria-label="Main">
      <button className="mark" aria-label="EnhancedExtract, Library" onClick={() => nav({ name: "library" })}><img src={logo} alt="" /></button>
      {item("library", "Library", { name: "library" })}
      {item("extract", "Extract archive", { name: "rar" })}
      {item("disc", "Install from ISO", { name: "iso" })}
      {item("jobs", running ? `Jobs, ${running} running` : "Jobs", { name: "jobs" }, running > 0 ? "now" : "")}
      <span className="rail-ind" aria-hidden="true" style={{ transform: `translateY(${64 + Math.max(0, idx) * 48 + 12}px)`, opacity: idx < 0 ? 0 : 1 }} />
      <span className="grow" />
      <button className="ri" aria-pressed={fx} aria-label={fx ? "Effects on" : "Effects off"} onClick={() => setFx(!fx)}>
        <Icon name={fx ? "fx" : "fxoff"} /><span className="tip">{fx ? "Effects on: click for a still, lighter look" : "Effects off: click to turn them on"}</span>
      </button>
      <button className="ri" aria-expanded={sysOpen} aria-controls="sys-panel" aria-label={sysBad ? "System check: something is missing" : "System check"} onClick={() => setSysOpen((o) => !o)}>
        <Icon name="system" />{sysBad && <span className="badge bad" aria-hidden="true" />}<span className="tip">{sysBad ? "System check: something is missing" : "System check"}</span>
      </button>
      {sysOpen && <SystemPanel onClose={() => setSysOpen(false)} />}
      <span style={{ height: 8 }} />
    </nav>
  );
}

/** Popover from the rail: every requirement with its state, and a re-check that visibly runs. */
function SystemPanel({ onClose }: { onClose: () => void }) {
  const { system, recheck } = useApp();
  const [at, setAt] = useState("");
  const check = useAction(useCallback(async () => {
    await recheck();
    setAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }, [recheck]));
  useEffect(() => play("popup"), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const rows: [string, boolean | undefined, string][] = [
    ["UnRAR", system?.unrar, "needed for RAR sets"],
    ["7-Zip", system?.sevenzip, "needed for zip, 7z, tar and the other formats"],
    ["WinFsp driver", system?.winfsp, "needed for ISO installs"],
    ["fusepy", system?.fusepy, "needed for ISO installs"],
    ["Administrator", system?.admin, "needed for ISO installs"],
  ];
  return (
    <>
      <div className="sys-scrim" onClick={onClose} />
      <div className="sys-panel" id="sys-panel" role="dialog" aria-label="System check">
        <h2>System check</h2>
        {rows.map(([name, ok, why]) => (
          <div className="sys-row" key={name}>
            <span className={`dot ${ok == null ? "" : ok ? "ok" : "bad"}`} aria-hidden="true" />
            <span style={{ flex: 1 }}>{name}<small>{why}</small></span>
            <span className="muted">{ok == null ? "checking" : ok ? "ready" : "missing"}</span>
          </div>
        ))}
        <div className="sys-foot">
          <span className="muted">{at ? `Checked at ${at}` : ""}</span>
          <button className="btn" onClick={() => check.run()} disabled={check.busy}>{check.busy ? "Checking…" : "Check again"}</button>
        </div>
      </div>
    </>
  );
}

const CRUMB: Record<Route["name"], [string, string?]> = {
  library: ["Library"], rar: ["Extract"], rarJob: ["Jobs", "Extract"], iso: ["Install"], isoJob: ["Jobs", "Install"], jobs: ["Jobs"],
};

/** Title bar controls as in the first version: sound switch, minimize and a red EXIT, all cut
 *  buttons. No maximize. EXIT hides the window at once and closes after its sound has played. */
function TitleBar() {
  const { route } = useApp();
  const [a, b] = CRUMB[route.name];
  return (
    <header className="top" data-tauri-drag-region>
      <div className="crumb" data-tauri-drag-region>
        <img className="wordmark" src={wordmark} alt="EnhancedExtract" data-tauri-drag-region /><span className="sep" aria-hidden="true" />
        <span className={b ? "" : "here"} data-tauri-drag-region>{a}</span>
        {b && <><span aria-hidden="true">/</span><span className="here" data-tauri-drag-region>{b}</span></>}
      </div>
      <WindowControls />
    </header>
  );
}

export function Page({ title, sub, actions, children }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className="title">
        <div style={{ minWidth: 0 }}><h1 className="ellipsis">{typeof title === "string" ? <Decode text={title} /> : title}</h1>{sub && <p className="sub">{sub}</p>}</div>
        {actions && <div className="acts">{actions}</div>}
      </div>
      {children}
    </>
  );
}
