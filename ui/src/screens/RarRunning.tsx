import { useEffect, useRef, useState } from "react";
import { Page, useApp } from "../App";
import { EngineError, call, diskSpace, jobLogs, jobStatus } from "../engine";
import { GiB, drive, dur, flag, gb, int, setName, shortId, jobStarted } from "../format";
import { useAction, usePoll } from "../hooks";
import { Busy, Dialog, ErrorNote } from "../components/ui";
import { LogLines } from "./Jobs";

export function RarRunning({ id }: { id: string }) {
  const { nav, refreshJobs, announce } = useApp();
  const job = usePoll(() => jobStatus(id), 1000);
  const logs = usePoll(() => jobLogs(id, 6, ["log", "event", "warning", "error"]), 3000);
  const [stopAsk, setStopAsk] = useState(false);
  const s = job.data;
  const argv = s?.argv ?? [];
  const path = argv[2] ?? "";
  const del = argv.includes("--delete");
  const verifyJob = argv[1] === "verify";
  const dest = flag(argv, "--dest") ?? (s?.result?.dest as string | undefined) ?? "";
  const p = s?.progress;
  const running = s?.state === "running";

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
  // Progress only exists while running; a finished job reports its totals in the result.
  const parts = p?.parts ?? (s?.result?.parts as number | undefined) ?? 0, part = p?.part ?? 0;

  return (
    <Page title={name}
      sub={<>{verifyJob ? "Verifying" : <>Extracting to <span className="mono">{dest || "…"}</span></>} · job <span className="mono">{shortId(s?.id ?? id)}</span> · started {jobStarted(s?.id ?? id)}{del ? " · parts are deleted as they're used" : ""}</>}
      actions={<>
        <button className="tlink" onClick={() => nav({ name: "library" })}>Back to library</button>
        {running && <button className="btn btn-danger" onClick={() => setStopAsk(true)}>Stop</button>}
      </>}>
      <ErrorNote error={job.error} onRetry={job.refresh} />
      {s && (s.state === "failed" || s.state === "died") && (
        <ErrorNote error={new EngineError(s.job_exit_code ?? 1, s.result?.error ?? s.stderr ?? "The job stopped.", s.result?.fix)}
          onRetry={path ? () => nav({ name: "rar", path }) : undefined} />
      )}
      {s?.state === "done" && (
        <div className="notice ok" role="status">
          <span>{verifyJob ? "Every part checked out. Nothing was written." : <>Done: {s.result?.files != null ? `${int(s.result.files)} files` : "all files"} in <span className="mono">{dest}</span>{del ? ", and every part was deleted." : "."}</>}</span>
        </div>
      )}

      <section className="hero brand" aria-label="Progress">
        <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", gap: 40, alignItems: "end" }}>
          <div>
            <div className="l" style={{ fontWeight: 600 }}>{verifyJob || phase === "verifying" ? "Verified" : s?.state === "done" ? "Extracted" : "Extracting"}</div>
            <div className="big-figure">{s ? `${Math.floor(pct)}%` : "…"}</div>
          </div>
          <div className="strip" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", paddingBottom: 6 }}>
            <div><span className="l">Time left</span><span className="v">{running && p?.eta_s != null ? dur(p.eta_s) : "—"}</span></div>
            <div><span className="l">Files</span><span className="v">{p?.files ? <>{int(p.files_done ?? 0)}<span className="unit">/ {int(p.files)}</span></> : s?.result?.files != null ? int(s.result.files) : "—"}</span></div>
            <div><span className="l">Running for</span><span className="v">{s ? dur(p?.elapsed_s ?? s.elapsed_s) : "—"}</span></div>
          </div>
        </div>
        <div className="track big" style={{ marginTop: 22 }} role="progressbar" aria-valuenow={Math.floor(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
          <div className="fill" style={{ width: `${pct}%` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 24, marginTop: 22 }}>
          {!verifyJob ? (
            <div className="tabs" style={{ borderBottom: 0 }} aria-label="Steps">
              {argv.includes("--no-verify") ? null : <span className="tab" aria-current={phase === "verifying" ? "step" : undefined}>{phase === "verifying" ? "Verifying" : "Verified"}</span>}
              <span className="tab" aria-current={phase === "extracting" ? "step" : undefined}>Extracting</span>
              {del && <span className="tab" aria-current={phase === "done" ? "step" : undefined}>Parts deleted</span>}
            </div>
          ) : <span />}
          <span className="small" style={{ fontWeight: 600 }}>{parts ? `${parts} parts${del ? " · each deleted once used" : ""}` : ""}</span>
        </div>
        {parts > 0 && (
          <div className="tape" style={{ marginTop: 14 }} role="img" aria-label={`${parts} parts: ${s?.state === "done" ? parts : Math.max(0, part - 1)} used${running ? `, part ${part} reading now` : ""}`}>
            {Array.from({ length: parts }, (_, i) => i + 1).map((n) => {
              const used = s?.state === "done" || n < part, now = running && n === part;
              return <i key={n} title={`Part ${n}: ${used ? (del && phase !== "verifying" ? "used and deleted" : "used") : now ? "reading now" : "waiting"}`}
                className={used ? (del && phase !== "verifying" ? "gone" : "used") : now ? "now" : ""} />;
            })}
          </div>
        )}
      </section>

      <div className="cols wide-left">
        <section className="card" aria-labelledby="fs">
          <div className="ch"><h2 id="fs">Free space on {drive(dest || path)}</h2>
            {series.length > 0 && <span className="meta">now <span className="num">{gb(series[series.length - 1].free)}</span> GB · lowest <span className="num">{gb(Math.min(...series.map((x) => x.free)))}</span> GB</span>}</div>
          {series.length > 1 ? <FreeChart series={series} /> : <p className="muted">{running ? "Sampling every 2 seconds while the job runs…" : "Shown while a job runs."}</p>}
          {del && series.length > 1 && <p className="muted small" style={{ marginTop: 10 }}>Each dip is a part being unpacked; each step back up is that part being deleted.</p>}
        </section>
        <section className="card" aria-labelledby="lg">
          <div className="ch"><h2 id="lg">Log</h2><button className="tlink" onClick={() => nav({ name: "jobs", id })}>Full log</button></div>
          <LogLines events={logs.data} />
        </section>
      </div>

      {stopAsk && (
        <Dialog title={`Stop extracting ${name}?`} onClose={() => setStopAsk(false)} actions={<>
          <button className="btn" data-autofocus onClick={() => setStopAsk(false)}>Keep going</button>
          <button className="btn btn-danger solid" onClick={() => stop.run()} disabled={stop.busy}><Busy busy={stop.busy}>Stop</Busy></button>
        </>}>
          <p className="soft">{del ? `Parts already used are deleted and stay deleted; the ${Math.max(0, parts - part + 1)} parts not yet used are kept. The files extracted so far stay in the folder.` : "The parts are kept. The files extracted so far stay in the folder."}</p>
          <ErrorNote error={stop.error} />
        </Dialog>
      )}
    </Page>
  );
}


/** One series, 4-5 round GB ticks, minutes along the bottom, a dot at now. */
function FreeChart({ series }: { series: { t: number; free: number }[] }) {
  const W = 520, H = 150, L = 40, R = 510, T = 10, B = 130;
  const vals = series.map((x) => x.free / GiB);
  const step = niceStep((Math.max(...vals) - Math.min(...vals)) || 1);
  const lo = Math.floor(Math.min(...vals) / step) * step, hi = Math.max(lo + 4 * step, Math.ceil(Math.max(...vals) / step + 0.25) * step);
  const tEnd = Math.max(60, series[series.length - 1].t);
  const X = (t: number) => L + (t / tEnd) * (R - L), Y = (v: number) => B - ((v - lo) / (hi - lo)) * (B - T);
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => lo + i * step);
  const mins = Math.max(1, Math.ceil(tEnd / 60 / 5));
  const xt = Array.from({ length: Math.floor(tEnd / 60 / mins) + 1 }, (_, i) => i * mins);
  const last = series[series.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Free space over time, in GB" style={{ display: "block", font: "11px var(--font)" }}>
      {ticks.map((v) => <g key={v}><line x1={L} x2={R} y1={Y(v)} y2={Y(v)} stroke="#2b2b2e" /><text x={L - 8} y={Y(v) + 4} fill="#8a8c92" textAnchor="end">{+v.toFixed(1)}</text></g>)}
      {xt.map((m) => <text key={m} x={X(m * 60)} y={H - 2} fill="#8a8c92" textAnchor={m === 0 ? "start" : "middle"}>{m === 0 ? "0 min" : m}</text>)}
      <polyline points={series.map((x) => `${X(x.t).toFixed(1)},${Y(x.free / GiB).toFixed(1)}`).join(" ")} fill="none" stroke="#f2f2f3" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={X(last.t)} cy={Y(last.free / GiB)} r={3} fill="var(--accent)" />
    </svg>
  );
}
function niceStep(range: number) {
  const raw = range / 4, p = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 5, 10].find((m) => m * p >= raw) ?? 10) * p;
}
