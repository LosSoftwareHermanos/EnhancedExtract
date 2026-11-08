import { useEffect, useRef, useState } from "react";
import { Decode, Num } from "../fx/motion";
import { Page, useApp } from "../App";
import { call, diskSpace, jobLogs, jobStatus } from "../engine";
import { GiB, drive, dur, flag, gb, int, isRar, setName, shortId, jobStarted } from "../format";
import { useAction, usePoll } from "../hooks";
import { Busy, Dialog, ErrorNote, Outcome } from "../components/ui";
import { LogLines } from "./Jobs";
import { play, useProgressSound } from "../sound";

export function RarRunning({ id }: { id: string }) {
  const { nav, refreshJobs, announce } = useApp();
  const job = usePoll(() => jobStatus(id), 1000);
  const logs = usePoll(() => jobLogs(id, 6, ["log", "event", "warning", "error"]), 3000);
  const [stopAsk, setStopAsk] = useState(false);
  const s = job.data;
  const argv = s?.argv ?? [];
  const path = argv[2] ?? "";
  const generic = !!path && !isRar(path);
  const del = argv.includes("--delete");
  const early = argv.includes("--early-delete");
  const resumable = !!s?.result?.resumable;
  const lost = Array.isArray(s?.result?.lost) ? (s.result.lost as string[]) : [];
  const verifyJob = argv[1] === "verify";
  const dest = flag(argv, "--dest") ?? (s?.result?.dest as string | undefined) ?? "";
  const p = s?.progress;
  const running = s?.state === "running";
  useProgressSound(running);
  // Seen running on this screen: the end result then sounds when it shows (not when opening an old job).
  const sawRunning = useRef(false);
  if (running) sawRunning.current = true;

  // Free space on the destination drive, sampled while the job runs: shows the disk staying safe.
  const [series, setSeries] = useState<{ t: number; free: number }[]>([]);
  const t0 = useRef(Date.now());
  useEffect(() => {
    if (!running || !(dest || path)) return;
    const tick = async () => { const d = await diskSpace(dest || path); if (d) setSeries((x) => [...x.slice(-600), { t: (Date.now() - t0.current) / 1000, free: d.free }]); };
    tick();
    const h = setInterval(tick, 2000);
    return () => clearInterval(h);
  }, [running, dest, path]);

  const prev = useRef(s?.state);
  useEffect(() => {
    if (prev.current === "running" && s && s.state !== "running") announce(s.state === "done" ? "Extraction finished." : "Extraction failed.");
    prev.current = s?.state;
  }, [s?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useAction(async () => { await call(["jobs", "stop", id], { allow: [1] }); setStopAsk(false); job.refresh(); refreshJobs(); });

  const name = path ? setName(path) : "…";
  const pct = s?.state === "done" ? 100 : p?.overall ?? 0;
  const phase = s?.state === "done" ? "done" : p?.phase ?? (verifyJob ? "verifying" : "extracting");
  // Keep the last recorded position after a stop; successful jobs use result totals.
  const verified = !verifyJob && !argv.includes("--no-verify");
  const parts = p?.parts ?? (s?.result?.parts as number | undefined) ?? 0, part = p?.part ?? 0;

  return (
    <Page title={name}
      sub={<>{verifyJob ? "Verifying" : <>Extracting to <span className="mono">{dest || "…"}</span></>} · job <span className="mono">{shortId(s?.id ?? id)}</span> · started {jobStarted(s?.id ?? id)}{del ? (p?.whole || s?.result?.format ? " · the archive is deleted once it's out" : early ? " · each part is deleted as soon as it's read" : " · parts are deleted as their files finish") : ""}</>}
      actions={<>
        <button className="btn" onClick={() => nav({ name: "library" })}>Back to library</button>
        {running && <button className="btn btn-danger" onClick={() => setStopAsk(true)}>Stop</button>}
      </>}>
      <ErrorNote error={job.error} onRetry={job.refresh} />
      {s && (s.state === "failed" || s.state === "died") && (
        <Outcome ok={false} fresh={sawRunning.current}
          title={s.job_exit_code === 130 ? "Stopped" : verifyJob ? "Verification failed" : "Extraction failed"}
          actions={path && <button className="btn btn-danger" onClick={() => nav({ name: "rar", path })}>{resumable ? "Resume" : "Try again"}</button>}>
          {resumable
            ? <>{s.job_exit_code === 130 ? "Stopped by you." : s.result?.error ?? "The job stopped."} Files extracted so far are kept{early ? ", except the one that was being extracted" : ""}. Resume continues where it left off.</>
            : <>{s.result?.error ?? s.stderr ?? "The job stopped."}{s.result?.fix && <div className="mono small muted" style={{ marginTop: 4, wordBreak: "break-all" }}>{s.result.fix}</div>}</>}
        </Outcome>
      )}
      {s?.state === "done" && (
        <Outcome ok fresh={sawRunning.current} title={verifyJob ? "Verification passed" : "Extraction complete"}>
          {verifyJob ? "Every part checked out. Nothing was written." : <>{s.result?.files != null ? `${int(s.result.files)} files` : "All files"} in <span className="mono">{dest}</span>{del ? (p?.whole || s.result?.format ? ", and the archive was deleted." : ", and every part was deleted.") : "."}</>}
        </Outcome>
      )}
      {s?.state === "done" && lost.length > 0 && (
        <div className="notice" role="alert"><span>{lost.length} file{lost.length === 1 ? "" : "s"} couldn't be recovered: the start was in a part deleted early. First: <span className="mono">{lost[0]}</span></span></div>
      )}

      <section className="hero brand" aria-label="Progress">
        <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", gap: 40, alignItems: "end" }}>
          <div>
            <div className="l" style={{ fontWeight: 600 }}>{verifyJob || phase === "verifying" ? "Verified" : s?.state === "done" ? "Extracted" : "Extracting"}</div>
            <div className="big-figure">{s ? <Num value={pct} format={(n) => `${Math.floor(n)}%`} /> : "…"}</div>
          </div>
          <div className="strip" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))", paddingBottom: 6 }}>
            <div><span className="l">Time left</span><span className="v">{running && p?.eta_s != null ? dur(p.eta_s) : "—"}</span></div>
            <div><span className="l">Running for</span><span className="v">{s ? dur(p?.elapsed_s ?? s.elapsed_s) : "—"}</span></div>
          </div>
        </div>
        <div className="track big" style={{ marginTop: 22 }} role="progressbar" aria-valuenow={Math.floor(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
          <div className="fill" style={{ transform: `scaleX(${pct / 100})` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 24, marginTop: 22 }}>
          {!verifyJob ? (
            <div className="tabs" style={{ borderBottom: 0 }} aria-label="Steps">
              {argv.includes("--no-verify") ? null : <span className="tab" aria-current={phase === "verifying" ? "step" : undefined}>Verification</span>}
              <span className="tab" aria-current={phase === "extracting" || phase === "done" ? "step" : undefined}>Extraction</span>
            </div>
          ) : <span />}
          <span className="small" style={{ fontWeight: 600 }}>{parts && !p?.whole && !s?.result?.format ? `${parts} parts${del ? (early ? " · each deleted once read" : " · each deleted once its files are out") : ""}` : ""}</span>
        </div>
        {parts > 0 && !p?.whole && !s?.result?.format && (
          <div className="tape" style={{ marginTop: 14 }} role="img" aria-label={`${parts} parts: ${s?.state === "done" ? parts : Math.max(0, part - 1)} done${running ? `, part ${part} reading now` : ""}`}>
            {Array.from({ length: parts }, (_, i) => i + 1).map((n) => {
              const verifying = verifyJob || phase === "verifying";
              const past = s?.state === "done" || n < part, now = running && n === part;
              // Verifying: parts checked turn green. Extracting: parts read turn red when deleted;
              // the ones still waiting stay green if they were verified.
              const state = verifying ? (past ? "ok" : now ? "now" : "")
                : past ? (del ? "gone" : "used") : now ? "now" : verified ? "ok" : "";
              return <Seg key={n} state={state} labels={parts <= 16}
                title={`Part ${n}: ${({ ok: "verified", gone: "read and deleted", used: "extracted", now: verifying ? "verifying now" : "extracting now", "": "waiting" } as Record<string, string>)[state]}`} />;
            })}
          </div>
        )}
      </section>

      <div className="cols wide-left">
        <section className="card" aria-labelledby="fs">
          <div className="ch"><h2 id="fs">Free space on {drive(dest || path)}</h2>
            {series.length > 0 && <span className="meta">now <span className="num">{gb(series[series.length - 1].free)}</span> GB · lowest <span className="num">{gb(Math.min(...series.map((x) => x.free)))}</span> GB</span>}</div>
          {series.length > 1 ? <FreeChart series={series} /> : <p className="muted">{running ? "Sampling every 2 seconds while the job runs…" : "Shown while a job runs."}</p>}
          {del && series.length > 1 && !p?.whole && !s?.result?.format && <p className="muted small" style={{ marginTop: 10 }}>Each dip is a part being unpacked; each step back up is that part being deleted.</p>}
        </section>
        <section className="card" aria-labelledby="lg">
          <div className="ch"><h2 id="lg">Log</h2></div>
          <LogLines events={logs.data} />
        </section>
      </div>

      {stopAsk && (
        <Dialog title={`Stop extracting ${name}?`} onClose={() => setStopAsk(false)} actions={<>
          <button className="btn" data-autofocus onClick={() => setStopAsk(false)}>Keep going</button>
          <button className="btn btn-danger solid" onClick={() => stop.run()} disabled={stop.busy}><Busy busy={stop.busy}>Stop</Busy></button>
        </>}>
          <p className="soft">{generic ? (del ? "Nothing is deleted unless extraction finishes cleanly, so the archive is kept. Files extracted so far stay in the folder." : "The archive is kept. Files extracted so far stay in the folder.")
            : !del ? "The parts are kept. The files extracted so far stay in the folder."
            : early ? `The file being extracted now is lost: its first parts are already deleted. Everything else extracted so far stays, and the ${Math.max(0, parts - part + 1)} parts not yet read are kept, so the rest can be resumed.`
            : "Nothing is lost. Files extracted so far stay in the folder, and every part still needed is kept. Open the set again to resume where it left off."}</p>
          <ErrorNote error={stop.error} />
        </Dialog>
      )}
    </Page>
  );
}


/** One part of the tape. A part that turns verified or deleted flashes from cyan into its colour,
 *  decodes its label in and makes a sound; parts already in that state when the screen opens don't. */
const SEG_LABEL: Record<string, string> = { ok: "Verified", gone: "Deleted" };
function Seg({ state, labels, title }: { state: string; labels: boolean; title: string }) {
  const prev = useRef(state);
  const [flip, setFlip] = useState(false);
  useEffect(() => {
    if (prev.current === state) return;
    // Only a part that was just being read flips; a stop turning the current part back to
    // "verified, waiting" is not news.
    const was = prev.current;
    prev.current = state;
    if (was !== "now" || (state !== "ok" && state !== "gone")) { setFlip(false); return; }
    setFlip(true);
    play(state === "ok" ? "part_verified" : "part_deleted");
    const t = setTimeout(() => setFlip(false), 900);
    return () => clearTimeout(t);
  }, [state]);
  const label = labels ? SEG_LABEL[state] : undefined;
  return <i className={`${state}${flip ? " flip" : ""}`} title={title}>{label && (flip ? <Decode text={label} /> : label)}</i>;
}

/** One series, 4-5 round GB ticks, minutes along the bottom. A glowing yellow line, and a cyan
 *  square at now. */
function FreeChart({ series }: { series: { t: number; free: number }[] }) {
  const W = 520, H = 150, L = 40, R = 506, T = 10, B = 130;
  const vals = series.map((x) => x.free / GiB);
  const step = niceStep((Math.max(...vals) - Math.min(...vals)) || 1);
  const lo = Math.floor(Math.min(...vals) / step) * step, hi = Math.max(lo + 4 * step, Math.ceil(Math.max(...vals) / step + 0.25) * step);
  const tEnd = Math.max(60, series[series.length - 1].t);
  const X = (t: number) => L + (t / tEnd) * (R - L), Y = (v: number) => B - ((v - lo) / (hi - lo)) * (B - T);
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => lo + i * step);
  const mins = Math.max(1, Math.ceil(tEnd / 60 / 5));
  const xt = Array.from({ length: Math.floor(tEnd / 60 / mins) + 1 }, (_, i) => i * mins);
  const last = series[series.length - 1];
  const lx = X(last.t), ly = Y(last.free / GiB);
  return (
    <svg className="free-chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Free space over time, in GB">
      <defs>
        <filter id="glow-y" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="2.4" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        <filter id="glow-c" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {ticks.map((v) => <g key={v}><line x1={L} x2={R} y1={Y(v)} y2={Y(v)} stroke="#2b2b2e" strokeDasharray="2 4" /><text x={L - 8} y={Y(v) + 4} textAnchor="end">{+v.toFixed(1)}</text></g>)}
      {xt.map((m) => <text key={m} x={X(m * 60)} y={H - 2} textAnchor={m === 0 ? "start" : "middle"}>{m === 0 ? "0 min" : m}</text>)}
      {/* Steps, not slopes: each sample holds flat until the next one, then the line goes straight up or down. */}
      <polyline points={series.map((x, i) => {
        const px = X(x.t).toFixed(1), py = Y(x.free / GiB).toFixed(1);
        return i === 0 ? `${px},${py}` : `${px},${Y(series[i - 1].free / GiB).toFixed(1)} ${px},${py}`;
      }).join(" ")} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="miter" strokeLinecap="square" filter="url(#glow-y)" />
      <rect className="now-mark" x={lx - 6} y={ly - 6} width={12} height={12} fill="none" stroke="var(--now)" strokeWidth={1} />
      <rect x={lx - 3.5} y={ly - 3.5} width={7} height={7} fill="var(--now)" filter="url(#glow-c)" />
    </svg>
  );
}
function niceStep(range: number) {
  const raw = range / 4, p = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 5, 10].find((m) => m * p >= raw) ?? 10) * p;
}
