import { useEffect, useRef, useState } from "react";
import { Page, useApp } from "../App";
import { EngineError, call, diskSpace, jobLogs, jobStatus, type Ev } from "../engine";
import { GiB, MiB, drive, dur, flag, gb, jobStarted, setName, shortId } from "../format";
import { useAction, usePoll } from "../hooks";
import { Busy, ConfirmDelete, Dialog, ErrorNote } from "../components/ui";
import { LogLines } from "./Jobs";

export function IsoRunning({ id }: { id: string }) {
  const { nav, refreshJobs, announce } = useApp();
  const job = usePoll(() => jobStatus(id), 1000);
  const logs = usePoll(() => jobLogs(id, 6, ["event", "warning", "error", "setup_started", "mounted"]), 3000);
  const [stopAsk, setStopAsk] = useState(false);
  const [delAsk, setDelAsk] = useState(false);
  const [free, setFree] = useState<{ now: number; low: number; start: number } | null>(null);
  const s = job.data;
  const argv = s?.argv ?? [];
  const path = argv[2] ?? "";
  const dir = flag(argv, "--install-dir") ?? "";
  const buffer = Number(flag(argv, "--buffer-gb") ?? 5);
  const installMb = Number(flag(argv, "--install-size-mb") ?? 0);
  const freeing = !argv.includes("--no-free");
  const running = s?.state === "running";
  const p = s?.progress;
  const r: Ev = s?.result ?? { type: "result" };

  useEffect(() => {
    if (!running || !path) return;
    const tick = async () => { const d = await diskSpace(dir || path); if (d) setFree((f) => ({ now: d.free, low: Math.min(f?.low ?? d.free, d.free), start: f?.start ?? d.free })); };
    tick();
    const h = setInterval(tick, 3000);
    return () => clearInterval(h);
  }, [running, dir, path]);

  const prev = useRef(s?.state);
  useEffect(() => {
    if (prev.current === "running" && s && s.state !== "running") announce(s.state === "done" ? "Install finished." : "Install failed.");
    prev.current = s?.state;
  }, [s?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useAction(async () => { await call(["jobs", "stop", id, "--force"], { allow: [1] }); setStopAsk(false); job.refresh(); refreshJobs(); });
  const delIso = useAction(async () => { await call(["iso", "delete", path, "--yes"]); setDelAsk(false); announce("ISO deleted."); });

  const name = path ? setName(path) : "…";
  const pct = s?.state === "done" ? 100 : p?.overall ?? 0;
  const total = (p?.bins ?? []).reduce((a, b) => a + b.size, 0);

  return (
    <Page title={name}
      sub={<>Installing to <span className="mono">{dir || "…"}</span> · job <span className="mono">{shortId(s?.id ?? id)}</span> · started {jobStarted(s?.id ?? id)}{freeing ? ` · freeing with a ${buffer} GB buffer` : " · ISO kept"}</>}
      actions={<>
        <button className="tlink" onClick={() => nav({ name: "library" })}>Back to library</button>
        {running && <button className="btn btn-danger" onClick={() => setStopAsk(true)}>Force stop</button>}
      </>}>
      <ErrorNote error={job.error} onRetry={job.refresh} />
      {s && (s.state === "failed" || s.state === "died") && <ErrorNote error={new EngineError(s.job_exit_code ?? 1, r.error ?? s.stderr ?? "The install stopped.", r.fix)} />}
      {s?.state === "done" && (
        <section className="card" aria-labelledby="fin">
          <div className="ch"><h2 id="fin">{name} is installed</h2><span className="meta">took {dur(s.elapsed_s)}</span></div>
          <div className="kv"><span><span className="dot" style={{ background: "var(--positive)" }} />Setup exit code</span><span className="num muted">{r.setup_exit_code ?? 0}</span></div>
          <div className="kv"><span><span className="dot" style={{ background: "var(--positive)" }} />Setup log reports success</span><span className="muted">ok</span></div>
          <div className="kv"><span><span className="dot" style={{ background: (r.unread?.length ? "var(--warning)" : "var(--positive)") }} />Every .bin read to the end</span><span className="muted">{r.unread?.length ? `not: ${r.unread.join(", ")}` : "yes"}</span></div>
          <div className="kv" style={{ marginTop: 12 }}>
            <span className="soft">{r.iso_deleted_bytes ? <>The ISO was deleted: <span className="num">{gb(r.iso_deleted_bytes)}</span> GB given back.</> : "Launch the game once before deleting the ISO."}</span>
            {!r.iso_deleted_bytes && <button className="btn btn-danger" onClick={() => setDelAsk(true)}>Delete ISO</button>}
          </div>
          <ErrorNote error={delIso.error} />
        </section>
      )}

      <section className="card" aria-label="Progress">
        <div className="strip">
          <div><span className="l">Setup has read</span><span className="v lead">{s ? `${Math.floor(pct)}%` : <span className="skel" />}</span><span className="s">{p?.bytes_read != null ? `${gb(p.bytes_read)} of ${gb(total)} GB` : " "}</span></div>
          <div><span className="l">Freed</span><span className="v">{p?.freed != null ? <>{gb(p.freed)}<span className="unit"> GB</span></> : "—"}</span><span className="s">given back to {drive(path)}</span></div>
          <div><span className="l">Installed</span><span className="v">{p?.installed != null ? <>{gb(p.installed)}<span className="unit"> GB</span></> : "—"}</span><span className="s">{installMb ? `of about ${gb(installMb * MiB)} GB` : " "}</span></div>
          <div><span className="l">Free on {drive(dir || path)}</span><span className="v">{free ? <>{gb(free.now)}<span className="unit"> GB</span></> : "—"}</span><span className="s">{free ? `lowest ${gb(free.low)} GB` : " "}</span></div>
        </div>
        <div className="track" style={{ marginTop: 18 }} role="progressbar" aria-valuenow={Math.floor(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Setup has read"><div className="fill" style={{ width: `${pct}%` }} /></div>
      </section>

      <section className="card" aria-labelledby="bn">
        <div className="ch"><h2 id="bn">The ISO, file by file</h2>
          <span className="meta" style={{ display: "flex", gap: 14 }}>
            <Key style={{ outline: "1px solid var(--control)", outlineOffset: -1 }} label="freed" />
            <Key style={{ background: "var(--soft)" }} label="buffer, kept" />
            <Key style={{ width: 2, background: "var(--accent)" }} label="setup is here" />
            <Key style={{ background: "var(--raised)" }} label="not read yet" />
          </span></div>
        {p?.bins?.length ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {p.bins.map((b) => {
              const fp = (b.freed / b.size) * 100, rp = (b.read / b.size) * 100;
              return (
                <div key={b.path} style={{ display: "grid", gridTemplateColumns: "140px minmax(0,1fr) 96px 48px", alignItems: "center", gap: 16 }}>
                  <span className="mono ellipsis">{b.path.replace(/^\//, "")}</span>
                  <div style={{ position: "relative", height: 18, borderRadius: 3, background: "var(--raised)", overflow: "hidden" }} role="img"
                    aria-label={`${b.path}: ${Math.floor(rp)}% read, ${gb(b.freed)} GB freed`}>
                    <span style={{ position: "absolute", inset: 0, width: `${fp}%`, outline: "1px solid var(--control)", outlineOffset: -1, background: "var(--surface)" }} />
                    <span style={{ position: "absolute", top: 0, bottom: 0, left: `${fp}%`, width: `${rp - fp}%`, background: "var(--soft)" }} />
                    {rp > 0 && rp < 100 && <span style={{ position: "absolute", top: 0, bottom: 0, left: `calc(${rp}% - 1px)`, width: 2, background: "var(--accent)" }} />}
                  </div>
                  <span className="num muted" style={{ textAlign: "right" }}>{gb(b.size)} GB</span>
                  <span className="num" style={{ textAlign: "right" }}>{Math.floor(rp)}%</span>
                </div>
              );
            })}
          </div>
        ) : <p className="muted">{running ? "Waiting for setup to start reading…" : "—"}</p>}
      </section>

      <div className="cols stretch">
        <section className="card" aria-labelledby="sf">
          <div className="ch"><h2 id="sf">Safety</h2><span className="meta">{p?.paused || p?.violations ? "needs attention" : "all clear"}</span></div>
          <div className="kv"><span><span className="dot" style={{ background: (p?.max_back ?? 0) < buffer * GiB ? "var(--positive)" : "var(--negative)" }} />Setup read back at most</span>
            <span className="num">{p?.max_back != null ? `${Math.round(p.max_back / MiB)}` : "—"}<span className="muted"> MB of a {buffer} GB buffer</span></span></div>
          <div className="kv"><span><span className="dot" style={{ background: p?.violations ? "var(--negative)" : "var(--positive)" }} />Reads of freed data blocked</span><span className="num">{p?.violations ?? 0}</span></div>
          <div className="kv"><span><span className="dot" style={{ background: p?.paused ? "var(--negative)" : "var(--positive)" }} />Freeing</span><span>{!freeing ? "off" : p?.paused ? "stopped for safety" : "active"}</span></div>
        </section>
        <section className="card" aria-labelledby="lg">
          <div className="ch"><h2 id="lg">Log</h2><button className="tlink" onClick={() => nav({ name: "jobs", id })}>Full log</button></div>
          <LogLines events={logs.data} />
        </section>
      </div>

      {stopAsk && (
        <Dialog title="Force stop while setup is running?" onClose={() => setStopAsk(false)} actions={<>
          <button className="btn" data-autofocus onClick={() => setStopAsk(false)}>Keep installing</button>
          <button className="btn btn-danger solid" onClick={() => stop.run()} disabled={stop.busy}><Busy busy={stop.busy}>Force stop</Busy></button>
        </>}>
          <p className="soft">Setup still reads from the virtual drive. Unmounting now makes setup fail{freeing ? ", and the parts of the ISO already freed are gone, so the ISO can't be used again" : ""}.</p>
          <ErrorNote error={stop.error} />
        </Dialog>
      )}
      {delAsk && <ConfirmDelete title={`Delete ${name}.iso?`} body="Launch the game once first. Deleting the ISO gives its space back; it can't be undone."
        tick="The game starts, delete the ISO" confirm="Delete ISO" onClose={() => setDelAsk(false)} onConfirm={() => delIso.run()} />}
    </Page>
  );
}

function Key({ style, label }: { style: React.CSSProperties; label: string }) {
  return <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 14, height: 10, borderRadius: 2, ...style }} />{label}</span>;
}
