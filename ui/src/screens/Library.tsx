import { useCallback, useEffect, useState } from "react";
import { Page, jobRoute, useApp } from "../App";
import { call, diskSpace, inTauri, ofType, pickFolder, relaunchAsAdmin, type FoundIso, type JobSnap, type RarSet } from "../engine";
import { basename, drive, dur, gb, setName } from "../format";
import { useAction, useStored } from "../hooks";
import { Busy, Check, ErrorNote } from "../components/ui";

interface Row { key: string; name: string; kind: "RAR" | "ISO"; detail: string; file: string; size: number; missing: number[]; wasFreed?: boolean }

export function Library() {
  const { nav, jobs, system, recheck } = useApp();
  const [folder, setFolder] = useStored("ee.folder", inTauri ? "" : "D:\\Downloads");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [scannedAt, setScannedAt] = useState<string>("");
  const [disk, setDisk] = useState<{ free: number; total: number } | null>(null);

  const scan = useAction(useCallback(async () => {
    if (!folder) return;
    const out = await call(["scan", folder, "--depth", "2"]);
    const sets = ofType(out, "rar_set") as unknown as RarSet[];
    const isos = ofType(out, "found_iso") as unknown as FoundIso[];
    setRows([
      ...sets.map((s) => ({ key: s.first, name: setName(s.first), kind: "RAR" as const, file: basename(s.first), size: s.size, missing: s.missing,
        detail: s.missing.length ? `${s.parts} of ${s.parts + s.missing.length} parts` : `${s.parts} parts` })),
      ...isos.map((i) => ({ key: i.path, name: setName(i.path), kind: "ISO" as const, file: basename(i.path), size: i.size, missing: [], wasFreed: i.was_freed, detail: "ISO image" })),
    ]);
    setScannedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    setDisk(await diskSpace(folder));
  }, [folder]));

  useEffect(() => { scan.run(); }, [folder]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "F5") { e.preventDefault(); scan.run(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [scan.run]);

  const choose = async () => { const f = await pickFolder(folder || undefined); if (f) setFolder(f); };
  const running = (jobs ?? []).filter((j) => j.state === "running");
  const jobFor = (path: string) => running.find((j) => (j.argv ?? []).includes(path));

  if (!folder)
    return (
      <Page title="Library" sub="Pick the folder your downloads land in. EnhancedExtract lists every RAR set and ISO in it, and reads nothing until you choose one.">
        <section className="card" style={{ maxWidth: 640 }}>
          <div className="ch"><h2>No folder yet</h2></div>
          <p className="soft" style={{ marginBottom: 16 }}>You can also drop a .rar part or an .iso anywhere on this window, or press Ctrl+O.</p>
          <button className="btn btn-primary" onClick={choose}>Choose folder</button>
        </section>
      </Page>
    );

  const need = (rows ?? []).filter((r) => r.missing.length || r.wasFreed).length;
  const ready = (rows ?? []).length - need - (rows ?? []).filter((r) => jobFor(r.key)).length;
  const summary = rows == null ? "Scanning…" : rows.length === 0 ? `Nothing to unpack in ${folder}.`
    : `${rows.length} ${rows.length === 1 ? "set" : "sets"} in ${folder}. ${running.length} running, ${Math.max(0, ready)} ready${need ? `, ${need} ${need === 1 ? "needs" : "need"} you` : ""}.`;

  return (
    <Page title="Library" sub={summary} actions={<>
      {scannedAt && <span className="stamp">Scanned {scannedAt}</span>}
      <button className="btn" onClick={choose}>Change folder</button>
      <button className="btn" onClick={() => scan.run()} disabled={scan.busy} title="F5"><Busy busy={scan.busy}>{scan.busy ? "Scanning" : "Rescan"}</Busy></button>
    </>}>
      <div className="main-rail">
        <section className="card" style={{ display: "flex", flexDirection: "column" }} aria-labelledby="lib">
          <div className="ch"><h2 id="lib" className="ellipsis">Found in {folder}</h2><span className="meta">Drop a .rar or .iso on the window</span></div>
          <ErrorNote error={scan.error} onRetry={() => scan.run()} />
          {!scan.error && <SetTable rows={rows} jobFor={jobFor} />}
          {rows && rows.length > 0 && (
            <div className="lib-row" style={{ marginTop: "auto", height: 44, borderTop: "1px solid var(--border)" }}>
              <span className="muted">{rows.length} sets</span>
              <span className="num" style={{ textAlign: "right" }}>{gb(rows.reduce((a, r) => a + r.size, 0))}<span className="muted"> GB</span></span><span /><span />
            </div>
          )}
        </section>

        <div className="stack">
          <section className="card" aria-labelledby="run">
            <div className="ch"><h2 id="run">Running</h2><button className="tlink" onClick={() => nav({ name: "jobs" })}>All jobs</button></div>
            {running.length === 0 ? <p className="muted">Nothing running. Jobs keep going when the window is closed.</p> : (
              <div className="rows">{running.slice(0, 3).map((j) => <RunningRow key={j.id} job={j} />)}</div>
            )}
          </section>
          <section className="card" aria-labelledby="drv">
            <div className="ch"><h2 id="drv">Drive {drive(folder)}</h2><span className="meta">free of total</span></div>
            {disk ? (<>
              <div className="kv"><span>{drive(folder)} free</span><span className="num">{gb(disk.free)}<span className="muted"> / {gb(disk.total)} GB</span></span></div>
              <div className="track" aria-hidden="true"><div className="fill grey" style={{ width: `${100 - (disk.free / disk.total) * 100}%` }} /></div>
            </>) : <p className="muted">—</p>}
          </section>
          <section className="card" aria-labelledby="pc">
            <div className="ch"><h2 id="pc">This PC</h2><button className="tlink" onClick={recheck}>Check again</button></div>
            <Check ok={system?.unrar ?? null} label="UnRAR" value={system?.unrarSource} />
            <Check ok={system ? system.winfsp && system.fusepy : null} label="Virtual drive (WinFsp)" value={system && !system.fusepy ? "fusepy missing" : undefined} />
            <Check ok={system?.admin ?? null} label="Administrator, for ISO installs" value={system?.admin ? "yes" : undefined}
              action={system && !system.admin ? <button className="tlink" onClick={() => relaunchAsAdmin()}>Restart as admin</button> : undefined} />
          </section>
        </div>
      </div>
    </Page>
  );
}

function SetTable({ rows, jobFor }: { rows: Row[] | null; jobFor: (p: string) => JobSnap | undefined }) {
  const { nav } = useApp();
  if (rows == null)
    return <div className="rows">{[0, 1, 2, 3].map((i) => <div key={i} className="lib-row" style={{ height: 64 }}><span className="skel" style={{ width: "50%" }} /><span className="skel" /><span className="skel" /><span /></div>)}</div>;
  if (rows.length === 0)
    return <div className="empty">No RAR sets or ISOs here (two folder levels deep). Choose another folder, or drop a file on the window.</div>;
  return (
    <>
      <div className="lib-row small muted" style={{ paddingBottom: 8 }}><span>Set</span><span style={{ textAlign: "right" }}>Packed</span><span>State</span><span /></div>
      <div className="rows">
        {rows.map((r) => {
          const job = jobFor(r.key);
          const pct = job?.progress?.overall;
          const [cls, text] = job ? ["neu", `${r.kind === "ISO" ? "Installing" : job.progress?.phase === "verifying" ? "Verifying" : "Extracting"}${pct != null ? ` · ${Math.floor(pct)}%` : ""}`]
            : r.missing.length ? ["neg", `Part ${r.missing.join(", ")} missing`]
            : r.wasFreed ? ["warn", "Partly freed earlier"] : ["pos", "Ready"];
          const [label, go] = job ? ["Open", () => nav(jobRoute(job))]
            : r.missing.length ? ["Details", () => nav({ name: "rar", path: r.key })]
            : [r.kind === "ISO" ? "Install" : "Extract", () => nav(r.kind === "ISO" ? { name: "iso", path: r.key } : { name: "rar", path: r.key })];
          return (
            <div key={r.key} className="lib-row" style={{ height: 64 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }} className="ellipsis">{r.name}</div>
                <div className="muted small ellipsis">{r.kind} · {r.detail} · <span className="mono">{r.file}</span></div>
              </div>
              <span className="num" style={{ textAlign: "right" }}>{gb(r.size)}<span className="muted"> GB</span></span>
              <span><span className={`pill ${cls}`}>{text}</span></span>
              <span style={{ textAlign: "right" }}><button className="tlink" onClick={go} aria-label={`${label} ${r.name}`}>{label}</button></span>
            </div>
          );
        })}
      </div>
    </>
  );
}

function RunningRow({ job }: { job: JobSnap }) {
  const { nav } = useApp();
  const p = job.progress;
  const iso = (job.argv?.[0] ?? "") === "iso";
  return (
    <button className="row-link" onClick={() => nav(jobRoute(job))} style={{ display: "block", width: "100%", textAlign: "left", background: "none", border: 0, padding: "10px 0", color: "inherit" }}>
      <div className="kv"><b className="ellipsis" style={{ fontWeight: 600 }}>{setName(job.argv?.[2] ?? job.command)}</b><span className="num">{p ? `${Math.floor(p.overall)}%` : "…"}</span></div>
      <div className="track"><div className="fill" style={{ width: `${p?.overall ?? 0}%` }} /></div>
      <div className="muted small" style={{ marginTop: 6 }}>
        {iso ? `Setup reading · ${p?.freed != null ? gb(p.freed) + " GB freed" : "starting"}` : `${p?.phase === "verifying" ? "Verifying" : "Extracting"} · ${p?.eta_s != null ? dur(p.eta_s) + " left" : "working out time left"}`}
      </div>
    </button>
  );
}
