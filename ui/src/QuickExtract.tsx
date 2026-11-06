import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { call, EngineError, jobStatus, jobsList, type JobSnap } from "./engine";
import { basename, dur, gb } from "./format";
import "./quick-extract.css";

export interface ShellRequest { archive: string; delete: boolean }
type State =
  | { kind: "busy"; message: string }
  | { kind: "confirm"; dest: string; steps: string[]; deletes: string[]; needed: number; free: number }
  | { kind: "password"; message: string }
  | { kind: "job"; id: string; dest: string; snapshot: JobSnap | null }
  | { kind: "error"; message: string };

const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const pathKey = (path: string) => path.replace(/^\\\\\?\\/, "").toLowerCase();

export function QuickExtract({ request }: { request: ShellRequest }) {
  const [state, setState] = useState<State>({ kind: "busy", message: "Checking the archive…" });
  const [password, setPassword] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [stopAsk, setStopAsk] = useState(false);
  const [notice, setNotice] = useState("");
  const secret = useRef("");
  const initialized = useRef(false);
  const acting = useRef(false);
  const args = (dest: string, extra: string[]) => ["rar", "extract", request.archive, "--dest", dest,
    ...(request.delete ? ["--delete"] : []), ...(secret.current ? ["--password-stdin"] : []), ...extra];
  const options = () => ({ stdin: secret.current || undefined });

  const fail = (error: unknown) => {
    if (error instanceof EngineError && error.code === 3) {
      setState({ kind: "password", message: secret.current ? "Password incorrect. Try again." : "This archive needs a password." });
    } else setState({ kind: "error", message: message(error) });
  };

  async function prepare() {
    if (acting.current) return;
    acting.current = true;
    setAcknowledged(false);
    setState({ kind: "busy", message: "Checking the archive and available space…" });
    try {
      // Reopen an existing extraction rather than starting it a second time.
      const existing = (await jobsList(10000)).find(j => j.state === "running" && j.argv?.[0] === "rar"
        && j.argv[1] === "extract" && pathKey(j.argv[2] ?? "") === pathKey(request.archive));
      if (existing) {
        const i = existing.argv?.indexOf("--dest") ?? -1;
        setState({ kind: "job", id: existing.id, dest: i >= 0 ? existing.argv?.[i + 1] ?? "" : "", snapshot: existing });
        return;
      }
      const dest = await invoke<string>("shell_destination", { reserve: false });
      const plan = await call(args(dest, ["--dry-run"]), options());
      if (request.delete) {
        const steps = plan.events.find(e => e.type === "plan");
        const space = plan.events.find(e => e.type === "space");
        setState({ kind: "confirm", dest,
          steps: Array.isArray(steps?.steps) ? steps.steps.filter((s: unknown): s is string => typeof s === "string") : [],
          deletes: Array.isArray(steps?.deletes) ? steps.deletes.filter((s: unknown): s is string => typeof s === "string") : [],
          needed: typeof space?.needed === "number" ? space.needed : 0,
          free: typeof space?.free === "number" ? space.free : 0 });
      } else await start(false);
    } catch (error) { fail(error); }
    finally { acting.current = false; }
  }

  async function start(confirmed: boolean) {
    if (request.delete && !confirmed) return;
    setState({ kind: "busy", message: "Starting verification…" });
    const dest = await invoke<string>("shell_destination", { reserve: true });
    const out = await call(args(dest, ["--background", ...(confirmed ? ["--yes"] : [])]), options());
    if (typeof out.result?.job !== "string") throw new Error("The engine did not return a job ID.");
    setState({ kind: "job", id: out.result.job, dest, snapshot: null });
  }

  useEffect(() => {
    if (!initialized.current) { initialized.current = true; void prepare(); }
  }, []);

  const jobId = state.kind === "job" ? state.id : null;
  const running = state.kind === "job" && (!state.snapshot || state.snapshot.state === "running");
  useEffect(() => {
    if (!jobId || !running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const snapshot = await jobStatus(jobId);
        if (active) {
          setNotice("");
          setState(previous => previous.kind === "job" && previous.id === jobId ? { ...previous, snapshot } : previous);
          if (snapshot.state !== "running") {
            if (snapshot.state === "done") { secret.current = ""; setPassword(""); }
            return;
          }
        }
      } catch (error) { if (active) setNotice(`Could not update progress: ${message(error)}. Retrying…`); }
      if (active) timer = setTimeout(poll, 1000);
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId, running]);

  async function stop() {
    if (!jobId) return;
    try { await call(["jobs", "stop", jobId], { allow: [1, 130] }); setStopAsk(false); }
    catch (error) { setNotice(message(error)); }
  }
  const close = () => void getCurrentWindow().close();
  const snapshot = state.kind === "job" ? state.snapshot : null;
  const finished = snapshot && snapshot.state !== "running";
  const done = snapshot?.state === "done";
  const deleting = snapshot?.argv?.includes("--delete") ?? request.delete;
  const progress = done ? 100 : snapshot?.progress?.overall ?? 0;

  return <main className="quick-extract">
    <div className="quick-brand">ENHANCEDEXTRACT <span>QUICK EXTRACT</span></div>
    <h1>{done ? "Extraction complete" : finished ? snapshot.job_exit_code === 130 ? "Extraction stopped" : "Extraction failed" : request.delete ? "Extract and free space" : "Extract archive"}</h1>
    <p className="quick-path">{basename(request.archive)}</p>
    <div aria-live="polite" className="quick-content">
      {state.kind === "busy" && <p role="status">{state.message}</p>}
      {state.kind === "confirm" && <>
        <p>Output folder</p><p className="quick-path">{state.dest}</p>
        <ol>{state.steps.map(step => <li key={step}>{step}</li>)}</ol>
        <p>{gb(state.needed)} GB needed · {gb(state.free)} GB free</p>
        <details><summary>View {state.deletes.length} archive parts to delete</summary><ul>{state.deletes.map(path => <li className="quick-path" key={path}>{path}</li>)}</ul></details>
        <p className="quick-warning">Parts are deleted as extraction proceeds. If it fails or you stop it, deleted parts cannot be recovered.</p>
        <label><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} /> I agree to permanently delete {state.deletes.length} archive part(s).</label>
        <div className="quick-actions"><button className="btn" onClick={close}>Cancel</button>
          <button className="btn btn-primary" disabled={!acknowledged} onClick={() => {
            if (acting.current) return;
            acting.current = true;
            void start(true).catch(fail).finally(() => { acting.current = false; });
          }}>Verify, extract and delete parts</button></div>
      </>}
      {state.kind === "password" && <form onSubmit={e => { e.preventDefault(); secret.current = password; setPassword(""); void prepare(); }}>
        <p>{state.message}</p><label>Password<input autoFocus type="password" autoComplete="off" value={password} onChange={e => setPassword(e.target.value)} /></label>
        <div className="quick-actions"><button type="button" className="btn" onClick={close}>Cancel</button><button className="btn btn-primary" disabled={!password}>Continue</button></div>
      </form>}
      {state.kind === "job" && <>
        <p className="quick-path">{state.dest}</p>
        <p>{done ? "All files extracted successfully." : finished ? snapshot?.result?.error ?? snapshot?.stderr ?? "The job stopped before completion." : snapshot?.progress?.phase ?? "Preparing verification…"}</p>
        <progress aria-label="Extraction progress" max={100} value={progress} />
        <p>{Math.round(progress)}%{snapshot?.progress?.eta_s != null ? ` · about ${dur(snapshot.progress.eta_s)} remaining` : ""}</p>
        {snapshot?.warnings?.map(w => <p className="quick-warning" key={w}>{w}</p>)}
        {running && <p className="muted">You can close this window. Extraction continues in the background and remains available in the app’s Jobs screen.</p>}
        {stopAsk && <div className="quick-warning"><p>Stop extraction? Partial output will remain.{deleting ? " Deleted archive parts cannot be recovered." : ""}</p>
          <button className="btn" onClick={() => setStopAsk(false)}>Keep extracting</button> <button className="btn btn-danger" onClick={() => void stop()}>Stop extraction</button></div>}
        <div className="quick-actions">
          {running && !stopAsk && <button className="btn" onClick={() => setStopAsk(true)}>Stop…</button>}
          {done && <button className="btn btn-primary" onClick={() => void invoke("open_output", { path: state.dest }).catch(e => setNotice(message(e)))}>Open folder</button>}
          {finished && !done && snapshot?.job_exit_code === 3 && <button className="btn btn-primary" onClick={() => setState({ kind: "password", message: "Enter the archive password to try again." })}>Enter password</button>}
          <button className="btn" onClick={close}>{running ? "Close · keep extracting" : "Close"}</button>
        </div>
      </>}
      {state.kind === "error" && <><p role="alert" className="quick-warning">{state.message}</p><div className="quick-actions"><button className="btn" onClick={close}>Close</button><button className="btn btn-primary" onClick={() => void prepare()}>Try again</button></div></>}
      {notice && <p role="alert" className="quick-warning">{notice}</p>}
    </div>
  </main>;
}
