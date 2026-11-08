import { useEffect, useRef, useState, type ReactNode } from "react";
import { call, closeWindow, EngineError, jobStatus, jobsList, openFolder, shellDestination, type EngineOutput, type JobSnap } from "./engine";
import { archiveFormat, basename, dirname, drive, dur, int, isRar, setName, size } from "./format";
import { installSounds, play, preload, useProgressSound } from "./sound";
import logo from "./assets/logo-64.png";
import wordmark from "./assets/wordmark.png";
import { Options, WindowControls } from "./components/ui";
import { useStored } from "./hooks";
import "./quick-extract.css";

export interface ShellRequest { archive: string; delete: boolean }
interface Info { parts: number; files: number; unpacked: number }
/** The engine's dry run. A RAR set with delete on runs in "early" mode, like the main window and the
 *  first version: each part is deleted as soon as it has been read. "after" is every other format
 *  (zip, 7z, tar ...): the archive goes once extraction finished cleanly. */
interface Plan {
  dest: string; deletes: string[]; needed: number; free: number; neededSafe: number;
  mode: "safe" | "early" | "keep" | "after"; resume: boolean; done: number; files: number; lost: string[];
}
/** The two dry runs behind the options: deleting parts (null when that can't be planned) and keeping them. */
interface Plans { del: Plan | null; keep: Plan }
type State =
  | { kind: "busy"; message: string }
  | { kind: "confirm"; plans: Plans }
  | { kind: "password"; message: string }
  | { kind: "job"; id: string; dest: string; snapshot: JobSnap | null }
  | { kind: "error"; message: string };

const message = (error: unknown) => error instanceof Error ? error.message : String(error);
const pathKey = (path: string) => path.replace(/^\\\\\?\\/, "").toLowerCase();
const num = (value: unknown) => typeof value === "number" && isFinite(value) ? value : 0;
const strings = (value: unknown) => Array.isArray(value) ? value.filter((s): s is string => typeof s === "string") : [];
const plural = (n: number, word: string) => `${int(n)} ${word}${n === 1 ? "" : "s"}`;

function readPlan(out: EngineOutput, dest: string): Plan {
  const event = (type: string) => out.events.find(e => e.type === type);
  // A dry run stopped for space (exit 4) puts the space figures in its result instead.
  const plan = event("plan"), space = event("space") ?? out.result;
  const mode = plan?.mode === "early" ? "early" : plan?.mode === "keep" ? "keep" : plan?.mode === "after" ? "after" : "safe";
  return {
    dest: typeof out.result?.dest === "string" ? out.result.dest : dest,
    deletes: strings(plan?.deletes), needed: num(space?.needed), free: num(space?.free),
    neededSafe: num(space?.needed_safe), mode, resume: !!plan?.resume,
    done: num(plan?.done), files: num(plan?.files), lost: strings(plan?.lost),
  };
}

export function QuickExtract({ request }: { request: ShellRequest }) {
  const [state, setState] = useState<State>({ kind: "busy", message: "Reading the archive…" });
  const [info, setInfo] = useState<Info | null>(null);
  const [password, setPassword] = useState("");
  // The same two options as the main window. Delete starts as the Explorer menu item chose it
  // ("Extract" or "Extract & free space"); verify is remembered like in the main window.
  const [del, setDel] = useState(request.delete);
  const [verify, setVerify] = useStored("ee.rar.verify", true);
  const choice = useRef({ del: request.delete, verify });
  choice.current = { del, verify };
  const [stopAsk, setStopAsk] = useState(false);
  const [notice, setNotice] = useState("");
  const secret = useRef("");
  const initialized = useRef(false);
  const acting = useRef(false);
  // Deleting works like the main window: a RAR set's parts go as soon as each has been read.
  const args = (dest: string, extra: string[], c = choice.current) => ["archive", "extract", request.archive, "--dest", dest,
    ...(c.del ? ["--delete"] : []), ...(c.del && isRar(request.archive) ? ["--early-delete"] : []),
    ...(c.verify ? [] : ["--no-verify"]), ...(secret.current ? ["--password-stdin"] : []), ...extra];
  const options = () => ({ stdin: secret.current || undefined });

  const fail = (error: unknown) => {
    if (error instanceof EngineError && error.code === 3) {
      setState({ kind: "password", message: secret.current ? "That password didn’t work. Try again." : "This archive is protected with a password." });
    } else setState({ kind: "error", message: message(error) });
  };

  async function prepare() {
    if (acting.current) return;
    acting.current = true;
    setStopAsk(false);
    setState({ kind: "busy", message: "Reading the archive and checking free space…" });
    try {
      // Reopen an extraction of this archive that is already running rather than starting a second one.
      const existing = (await jobsList(10000)).find(j => j.state === "running" && (j.argv?.[0] === "archive" || j.argv?.[0] === "rar")
        && j.argv[1] === "extract" && pathKey(j.argv[2] ?? "") === pathKey(request.archive));
      if (existing) {
        const i = existing.argv?.indexOf("--dest") ?? -1;
        setState({ kind: "job", id: existing.id, dest: i >= 0 ? existing.argv?.[i + 1] ?? "" : "", snapshot: existing });
        return;
      }
      const dest = await shellDestination(false);
      // Plan both ways at once, so ticking Delete on or off only changes which figures show.
      // Not enough space (exit 4) still returns the figures; the button then says it doesn't fit.
      const dry = (d: boolean) => call(args(dest, ["--dry-run"], { del: d, verify: true }), { ...options(), allow: [4] });
      const [withDel, withoutDel] = await Promise.all([dry(true).catch(() => null), dry(false)]);
      const archive = (withDel ?? withoutDel).events.find(e => e.type === "archive");
      if (archive) setInfo({ parts: strings(archive.volumes).length, files: num(archive.files), unpacked: num(archive.unpacked) });
      const plans = { del: withDel ? readPlan(withDel, dest) : null, keep: readPlan(withoutDel, dest) };
      if (plans.del?.resume) setDel(true);          // a stopped delete run continues as one
      setState({ kind: "confirm", plans });
    } catch (error) { fail(error); }
    finally { acting.current = false; }
  }

  /** `plan` is the dry run for the options chosen. A resume goes back into its folder. */
  async function start(plan: Plan) {
    setState({ kind: "busy", message: plan.resume ? "Resuming…" : "Starting…" });
    const dest = plan.resume ? plan.dest : await shellDestination(true);
    const out = await call(args(dest, ["--background", ...(choice.current.del ? ["--yes"] : [])]), options());
    if (typeof out.result?.job !== "string") throw new Error("The engine did not return a job ID.");
    setState({ kind: "job", id: out.result.job, dest, snapshot: null });
  }

  useEffect(() => {
    if (!initialized.current) { initialized.current = true; void prepare(); }
  }, []);
  useEffect(() => { void preload(); return installSounds(); }, []);
  // Each new view (options, password, progress, error) slides in with the same sound as changing
  // screens in the main window. The "Reading…" step in between stays quiet.
  useEffect(() => {
    if (state.kind !== "busy") void preload().then(() => play("tab"));
  }, [state.kind]);

  const jobId = state.kind === "job" ? state.id : null;
  const running = state.kind === "job" && (!state.snapshot || state.snapshot.state === "running");
  useProgressSound(running);
  useEffect(() => {
    if (!jobId || !running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const snapshot = await jobStatus(jobId);
        if (active) {
          setNotice("");
          // A finished job reports no progress; keep the last one so the bar shows where it ended.
          setState(previous => previous.kind === "job" && previous.id === jobId
            ? { ...previous, snapshot: { ...snapshot, progress: snapshot.progress ?? previous.snapshot?.progress } } : previous);
          if (snapshot.state !== "running") {
            if (snapshot.state === "done") { secret.current = ""; setPassword(""); }
            return;
          }
        }
      } catch (error) { if (active) setNotice(`Couldn’t update progress (${message(error)}). Retrying…`); }
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
  const close = () => void closeWindow();

  const meta = info
    ? [info.parts > 1 ? plural(info.parts, "part") : archiveFormat(request.archive), info.files ? plural(info.files, "file") : "", size(info.unpacked)].filter(Boolean).join(" · ")
    : basename(request.archive);

  let body: ReactNode = null;
  let foot: ReactNode = null;

  if (state.kind === "busy") {
    body = <p className="qx-busy" role="status"><span className="spin" aria-hidden />{state.message}</p>;
    foot = <button className="btn" onClick={close}>Cancel</button>;
  }

  if (state.kind === "confirm") {
    const { plans } = state;
    const resume = !!plans.del?.resume;
    const deleting = (del || resume) && !!plans.del;
    const plan = deleting ? plans.del! : plans.keep;
    const generic = !isRar(request.archive);
    const count = plans.del?.deletes.length || info?.parts || 1;
    const fits = plan.needed <= plan.free;
    const submit = () => {
      if (acting.current || !fits) return;
      acting.current = true;
      void start(plan).catch(fail).finally(() => { acting.current = false; });
    };
    body = <>
      <Destination path={plan.dest}>
        <div className="qx-space">
          <div className="qx-meter" aria-hidden><i style={{ width: `${plan.free ? Math.min(100, Math.max(1.5, 100 * plan.needed / plan.free)) : 100}%`, background: fits ? undefined : "var(--negative)" }} /></div>
          <div className="qx-space-row">
            <span>Needs <b className="num">{size(plan.needed)}</b></span>
            <span><b className="num">{size(plan.free)}</b> free{drive(plan.dest) ? ` on ${drive(plan.dest)}` : ""}</span>
          </div>
        </div>
      </Destination>
      {resume && <div className="qx-note-card">
        <Shield />
        <div>
          <strong>Picks up where it stopped</strong>
          <span>{int(plan.done)} of {plural(plan.files, "file")} are already extracted. The rest continue from {count === 1 ? "the part" : `the ${count} parts`} left.</span>
        </div>
      </div>}
      {plan.lost.length > 0 && <div className="qx-alert warn" role="alert">
        <p>{plural(plan.lost.length, "file")} can’t be recovered: {plan.lost.length === 1 ? "its" : "their"} start was in a part deleted early. First: {basename(plan.lost[0])}</p>
      </div>}
      <Options free={plan.free} label="How to extract" options={[
        { label: generic ? "Verify the archive first (recommended)" : "Verify all parts first (recommended)", checked: verify, onChange: setVerify,
          note: "Reads everything and writes nothing, so a corrupt part stops the job before anything is deleted." },
        ...(plans.del ? [{ label: generic ? (count > 1 ? "Delete the parts once everything is out" : "Delete the archive once everything is out")
            : "Delete each part as soon as it has been extracted",
          checked: deleting, onChange: setDel, disabled: resume, needed: plans.del.needed,
          note: generic ? "It can't be freed while it's read, so its space comes back at the end. Nothing is deleted if anything goes wrong."
            : <>Needs <span className="num">{size(plans.del.needed)}</span> instead of <span className="num">{size(plans.keep.needed)}</span>. If extraction stops or crashes, the file being extracted is lost and its deleted parts must be downloaded again.</> }] : []),
      ]} />
    </>;
    foot = <>
      <button className="btn" onClick={close}>Cancel</button>
      <button className="btn btn-primary" disabled={!fits} title={fits ? undefined : "Not enough free space for this choice"} onClick={submit}>
        {resume ? "Resume" : deleting ? "Extract & delete" : "Extract"}</button>
    </>;
  }

  if (state.kind === "password") {
    const formId = "qx-password";
    body = <form id={formId} className="qx-password" onSubmit={e => { e.preventDefault(); if (!password) return; secret.current = password; setPassword(""); void prepare(); }}>
      <label className="lab">{state.message}
        <input className="field" autoFocus type="password" autoComplete="off" placeholder="Archive password" value={password} onChange={e => setPassword(e.target.value)} />
      </label>
    </form>;
    foot = <>
      <button type="button" className="btn" onClick={close}>Cancel</button>
      <button form={formId} className="btn btn-primary" disabled={!password}>Unlock</button>
    </>;
  }

  if (state.kind === "job") {
    const snap = state.snapshot;
    const argv = snap?.argv ?? args(state.dest, []);
    const verifies = !argv.includes("--no-verify");
    const deleting = argv.includes("--delete");
    const risky = argv.includes("--early-delete");
    const finished = !!snap && snap.state !== "running";
    const done = snap?.state === "done";
    const stopped = finished && snap?.job_exit_code === 130;
    const progress = snap?.progress;
    const pct = Math.max(0, Math.min(100, progress?.overall ?? 0));
    const phase = done ? "done" : verifies && (!progress || progress.phase === "verifying") ? "verify" : "extract";
    const segments = [
      ...(verifies ? [{ key: "verify", label: "Verify", weight: 1 }] : []),
      { key: "extract", label: deleting ? "Extract & free space" : "Extract", weight: 2 },
    ].map(s => {
      const past = done || (s.key === "verify" && phase === "extract");
      const now = !past && s.key === phase;
      return { ...s, fill: past ? 100 : now ? pct : 0, status: past ? "done" : now ? (finished ? "bad" : "now") : "wait" };
    });
    const result = snap?.result;
    const resumable = finished && !done && !!result?.resumable;
    const lost = strings(result?.lost);
    const deleted = num(result?.parts) - num(result?.parts_left);
    const status = done ? "Complete" : stopped ? "Stopped" : finished ? "Failed" : phase === "verify" ? "Verifying" : "Extracting";
    const tone = done ? "good" : finished ? "bad" : "now";

    body = <>
      <Destination path={state.dest} />
      <section className={`qx-run ${tone}`} aria-label="Progress">
        <div className="qx-run-top">
          <span className="qx-status">{status}</span>
          {!finished && progress?.eta_s != null && <span className="qx-eta">about <b className="num">{dur(progress.eta_s)}</b> left</span>}
        </div>
        <div className="qx-pct num" aria-live="off">{done ? 100 : Math.floor(pct)}<small>%</small></div>
        <div className="qx-segs" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={done ? 100 : Math.floor(pct)} aria-valuetext={`${status} ${done ? 100 : Math.floor(pct)}%`}>
          {segments.map(s => <div key={s.key} className={`qx-seg ${s.status}`} style={{ flexGrow: s.weight }}>
            <div className="qx-bar"><i style={{ transform: `scaleX(${s.fill / 100})` }} /></div>
            <span>{s.status === "done" && <Check />}{s.label}</span>
          </div>)}
        </div>
        <p className="qx-detail" role="status">
          {done ? <>{result?.files != null ? <>{plural(num(result.files), "file")} extracted{result.unpacked != null && <> · <span className="num">{size(num(result.unpacked))}</span></>}</> : "All files extracted."}
              {deleting && result?.parts != null && <> · {progress?.whole || num(result.parts) === 1 ? "archive" : plural(deleted, "archive part")} deleted</>}</>
            : finished ? null
            : progress ? <>{progress.whole ? null : <>Part <span className="num">{progress.part ?? 1}</span> of <span className="num">{progress.parts ?? "?"}</span></>}
                {phase === "extract" && progress.files ? <>{progress.whole ? null : " · "}<span className="num">{int(progress.files_done ?? 0)}</span> of <span className="num">{int(progress.files)}</span> files</> : null}</>
            : "Starting…"}
        </p>
      </section>
      {done && lost.length > 0 && <div className="qx-alert warn" role="alert">
        <p>{plural(lost.length, "file")} couldn’t be recovered: {lost.length === 1 ? "its" : "their"} start was in a part deleted early. First: {basename(lost[0])}</p>
      </div>}
      {finished && !done && <div className={resumable ? "qx-alert warn" : "qx-alert"} role="alert">
        <p>{stopped ? "Extraction was stopped." : result?.error ?? snap?.stderr ?? "The job ended before it finished."}</p>
        {resumable ? <p>Files extracted so far are kept. Resume to continue where it left off{risky ? ", except the file that was being extracted" : ""}.</p>
          : stopped ? <p>Files extracted so far are still in the folder.</p> : null}
      </div>}
      {snap?.warnings?.map(w => <p className="qx-alert warn" key={w}>{w}</p>)}
      {running && !stopAsk && <p className="qx-note">You can close this window. Extraction keeps going in the background, and you can follow it from the Jobs screen.</p>}
    </>;

    foot = stopAsk ? <>
      <p className="qx-ask">{risky ? "Stop now? The file being extracted is lost." : deleting && isRar(request.archive) ? "Stop now? You can resume later." : "Stop now? The archive and extracted files stay."}</p>
      <button className="btn" autoFocus onClick={() => setStopAsk(false)}>Keep going</button>
      <button className="btn btn-danger solid" onClick={() => void stop()}>Stop</button>
    </> : <>
      {running && <button className="btn btn-danger qx-left" onClick={() => setStopAsk(true)}>Stop</button>}
      {finished && !done && snap?.job_exit_code === 3 && <button className="btn" onClick={() => setState({ kind: "password", message: "Enter the archive password to try again." })}>Enter password</button>}
      <button className="btn" onClick={close}>{running ? "Hide" : "Close"}</button>
      {finished && !done && snap?.job_exit_code !== 3 && <button className="btn btn-primary" onClick={() => void prepare()}>{resumable ? "Resume" : "Try again"}</button>}
      {done && <button className="btn btn-primary" autoFocus onClick={() => void openFolder(state.dest).catch(e => setNotice(message(e)))}>Open folder</button>}
    </>;
  }

  if (state.kind === "error") {
    body = <div className="qx-alert" role="alert"><p>{state.message}</p></div>;
    foot = <>
      <button className="btn" onClick={close}>Close</button>
      <button className="btn btn-primary" onClick={() => void prepare()}>Try again</button>
    </>;
  }

  return <main className="qx">
    {/* The same title bar as the main window: no Windows frame, the app's own controls. */}
    <header className="top qx-top" data-tauri-drag-region>
      <div className="crumb" data-tauri-drag-region>
        <img className="wordmark" src={wordmark} alt="EnhancedExtract" data-tauri-drag-region /><span className="sep" aria-hidden="true" />
        <span className="here" data-tauri-drag-region>Quick extract</span>
      </div>
      <WindowControls />
    </header>
    <div className="qx-body">
      <header className="qx-head">
        <img src={logo} alt="" width={40} height={40} />
        <div>
          <h1 title={request.archive}>{setName(request.archive) || basename(request.archive)}</h1>
          <p className="qx-meta">{meta}</p>
        </div>
      </header>
      <div className="qx-content" key={state.kind}>{body}</div>
      {notice && <p role="alert" className="qx-alert warn">{notice}</p>}
    </div>
    <footer className="qx-foot">{foot}</footer>
  </main>;
}

function Destination({ path, children }: { path: string; children?: ReactNode }) {
  return <div className="qx-card">
    <div className="qx-dest" title={path}>
      <svg viewBox="0 0 24 24" aria-hidden><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2.2h8.4A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z" /></svg>
      <div>
        <span className="qx-label">Extract to</span>
        <strong>{basename(path) || path}</strong>
        <small>{dirname(path)}</small>
      </div>
    </div>
    {children}
  </div>;
}

function Check() {
  return <svg viewBox="0 0 16 16" aria-hidden className="qx-check"><path d="M3 8.5l3.2 3L13 4.5" /></svg>;
}

function Shield() {
  return <svg viewBox="0 0 24 24" aria-hidden className="qx-shield"><path d="M12 3l7 3v5.5c0 4.3-2.9 8-7 9.5-4.1-1.5-7-5.2-7-9.5V6z" /><path d="M8.8 12.2l2.2 2.1 4.3-4.6" /></svg>;
}
