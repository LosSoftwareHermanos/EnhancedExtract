import { useCallback, useEffect, useState } from "react";
import { Num } from "../fx/motion";
import { Page, jobRoute, useApp } from "../App";
import { call, diskSpace, inTauri, installFusepy, ofType, pickFolder, type FoundIso, type JobSnap, type RarSet } from "../engine";
import { basename, drive, gb, setName } from "../format";
import { useAction, useStored } from "../hooks";
import { Busy, ErrorNote } from "../components/ui";
import logo from "../assets/logo.png";

interface Row { key: string; name: string; kind: "RAR" | "ISO"; detail: string; file: string; size: number; count: number; missing: number[]; wasFreed?: boolean }

export function Library() {
  const { nav, jobs } = useApp();
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
      ...sets.map((s) => ({ key: s.first, name: setName(s.first), kind: "RAR" as const, file: basename(s.first), size: s.size, count: s.parts + s.missing.length, missing: s.missing,
        detail: s.missing.length ? `${s.parts} of ${s.parts + s.missing.length} parts` : `${s.parts} parts` })),
      ...isos.map((i) => ({ key: i.path, name: setName(i.path), kind: "ISO" as const, file: basename(i.path), size: i.size, count: 0, missing: [], wasFreed: i.was_freed, detail: "ISO image" })),
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
      <Page title="Library" sub="Your downloads, ready to unpack.">
        <section className="welcome cut" aria-labelledby="first">
          <img className="logo" src={logo} alt="" />
          <div>
            <h2 id="first">Point it at your downloads</h2>
            <p className="soft" style={{ maxWidth: "52ch", marginBottom: 20 }}>EnhancedExtract lists every multi-part RAR set and game ISO in a folder, checks each one, and unpacks it while giving the space back as it goes. Nothing is read until you pick a set.</p>
            <div className="acts" style={{ justifyContent: "flex-start" }}>
              <button className="btn btn-primary" onClick={choose}>Choose folder</button>
              <span className="muted">or drop a .rar part or an .iso on the window · Ctrl+O</span>
            </div>
          </div>
        </section>
      </Page>
    );

  const need = (rows ?? []).filter((r) => r.missing.length || r.wasFreed).length;
  const busy = (rows ?? []).filter((r) => jobFor(r.key)).length;
  const ready = (rows ?? []).length - need - busy;
  const total = (rows ?? []).reduce((a, r) => a + r.size, 0);

  return (
    <Page title="Library" sub={<span className="ellipsis" style={{ display: "block" }} title={folder}>{folder}</span>} actions={<>
      {scannedAt && <span className="stamp">Scanned {scannedAt}</span>}
      <button className="btn" onClick={choose}>Change folder</button>
      <button className="btn" onClick={() => scan.run()} disabled={scan.busy} title="F5"><Busy busy={scan.busy}>{scan.busy ? "Scanning" : "Rescan"}</Busy></button>
    </>}>
      <section className="hero brand" aria-label="Summary">
        <div className="strip" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
          <div><span className="l">Ready to unpack</span><span className="v lead">{rows ? <Num value={Math.max(0, ready)} format={(n) => String(Math.round(n))} /> : "…"}</span></div>
          <div><span className="l">Running</span><span className="v">{busy}</span>
            <span className="s">{busy ? <button className="tlink" onClick={() => nav({ name: "jobs" })}>See jobs</button> : "nothing running"}</span></div>
          <div><span className="l">Need you</span><span className="v">{rows ? need : "…"}</span><span className="s">{need ? "missing or freed parts" : "every set complete"}</span></div>
          <div><span className="l">In this folder</span><span className="v"><Num value={total} format={gb} /><span className="unit">GB</span></span><span className="s">{rows ? `${rows.length} ${rows.length === 1 ? "set" : "sets"}` : " "}</span></div>
          <div><span className="l">Free on {drive(folder)}</span><span className="v">{disk ? <><Num value={disk.free} format={gb} /><span className="unit">GB</span></> : "—"}</span><span className="s">{disk ? `of ${gb(disk.total)} GB` : " "}</span></div>
        </div>
      </section>
      <SystemNotice />
      <section className="card" aria-labelledby="lib">
        <div className="ch"><h2 id="lib">Sets</h2><span className="meta">Drop a .rar or .iso on the window to add one · F5 rescans</span></div>
        <ErrorNote error={scan.error} onRetry={() => scan.run()} />
        {!scan.error && <SetTable rows={rows} jobFor={jobFor} />}
      </section>
    </Page>
  );
}

/** What this PC is missing, with a way to fix it from here and a re-check that shows it ran. */
function SystemNotice() {
  const { system, recheck, announce } = useApp();
  const [checkedAt, setCheckedAt] = useState("");
  const check = useAction(useCallback(async () => {
    await recheck();
    setCheckedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
  }, [recheck]));
  const fuse = useAction(useCallback(async () => {
    await installFusepy();
    await recheck();
    announce("fusepy installed.");
  }, [recheck, announce]));

  if (!system || (system.unrar && system.winfsp && system.fusepy)) return null;
  const busy = check.busy || fuse.busy;
  return (
    <>
      <div className="notice err" role="status">
        <span style={{ flex: 1 }}>{!system.unrar ? "UnRAR wasn't found, so RAR sets can't be opened. Install WinRAR, then check again."
          : "ISO installs need the virtual drive: " + [!system.winfsp && "WinFsp isn't installed", !system.fusepy && "the fusepy package is missing"].filter(Boolean).join(" and ") + ". RAR extraction works."}
          {checkedAt && !busy && <span className="muted"> Still missing at {checkedAt}.</span>}</span>
        {system.unrar && !system.fusepy && (
          <button className="tlink" onClick={() => fuse.run()} disabled={busy}><Busy busy={fuse.busy}>{fuse.busy ? "Installing fusepy" : "Install fusepy"}</Busy></button>
        )}
        <button className="tlink" onClick={() => check.run()} disabled={busy}><Busy busy={check.busy}>{check.busy ? "Checking" : "Check again"}</Busy></button>
      </div>
      <ErrorNote error={fuse.error} onRetry={() => fuse.run()} />
    </>
  );
}

function SetTable({ rows, jobFor }: { rows: Row[] | null; jobFor: (p: string) => JobSnap | undefined }) {
  const { nav } = useApp();
  if (rows == null)
    return <div className="rows">{[0, 1, 2, 3].map((i) => <div key={i} className="lib-row" style={{ height: 72 }}><span className="skel" style={{ width: "50%" }} /><span className="skel" style={{ width: "100%" }} /><span className="skel" /><span className="skel" /><span /></div>)}</div>;
  if (rows.length === 0)
    return <div className="empty">No RAR sets or ISOs here (two folder levels deep). Choose another folder, or drop a file on the window.</div>;
  return (
    <>
      <div className="lib-row small muted" style={{ paddingBottom: 10 }}><span>Set</span><span>Parts</span><span style={{ textAlign: "right" }}>Packed</span><span>State</span><span /></div>
      <div className="rows stagger">
        {rows.map((r, ri) => {
          const job = jobFor(r.key);
          const pct = job?.progress?.overall;
          const [cls, text] = job ? ["neu live", `${r.kind === "ISO" ? "Installing" : job.progress?.phase === "verifying" ? "Verifying" : "Extracting"}${pct != null ? ` ${Math.floor(pct)}%` : ""}`]
            : r.missing.length ? ["neg", `Part ${r.missing.join(", ")} missing`]
            : r.wasFreed ? ["warn", "Partly freed earlier"] : ["pos", "Ready"];
          const [label, go] = job ? ["Open", () => nav(jobRoute(job))]
            : r.missing.length ? ["Details", () => nav({ name: "rar", path: r.key })]
            : [r.kind === "ISO" ? "Install" : "Extract", () => nav(r.kind === "ISO" ? { name: "iso", path: r.key } : { name: "rar", path: r.key })];
          const usedParts = job && r.kind === "RAR" ? Math.max(0, (job.progress?.part ?? 1) - 1) : 0;
          return (
            <div key={r.key} className="lib-row row-link" style={{ height: 72, margin: "0 -12px", padding: "0 12px", ["--i" as string]: ri }} onClick={go}>
              <div style={{ minWidth: 0 }}>
                <div className="set-name ellipsis">{r.name}</div>
                <div className="muted small ellipsis">{r.kind} · {r.detail} · {r.file}</div>
              </div>
              {r.kind === "RAR" ? (
                <div className="tape mini" role="img" aria-label={r.missing.length ? `${r.count} parts, part ${r.missing.join(", ")} missing` : `${r.count} parts, all present`}>
                  {Array.from({ length: Math.min(r.count, 40) }, (_, i) => i + 1).map((n) =>
                    <i key={n} style={{ ["--i" as string]: ri * 3 + n }} className={r.missing.includes(n) ? "missing" : n <= usedParts ? "done" : ""} />)}
                </div>
              ) : <span className="muted small">single image</span>}
              <span className="num" style={{ textAlign: "right", fontSize: 15 }}>{gb(r.size)}<span className="unit">GB</span></span>
              <span><span className={`pill ${cls}`}>{text}</span></span>
              <span style={{ textAlign: "right" }}>
                <button className={job || r.missing.length ? "tlink" : "btn"} onClick={(e) => { e.stopPropagation(); go(); }} aria-label={`${label} ${r.name}`}>{label}</button>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}

