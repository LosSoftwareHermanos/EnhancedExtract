import { useCallback, useEffect, useState } from "react";
import { Num } from "../fx/motion";
import { Page, jobRoute, useApp } from "../App";
import { call, diskSpace, inTauri, installFusepy, ofType, pickFolder, type FoundIso, type JobSnap, type OtherArchive, type RarSet } from "../engine";
import { archiveFormat, basename, drive, gb, setName } from "../format";
import { useAction, useStored } from "../hooks";
import { Busy, ErrorNote, Status } from "../components/ui";
import logo from "../assets/logo.png";

/** `label` is what the row shows as its type: RAR, ISO, ZIP, 7Z, TAR.GZ ... */
interface Row { key: string; name: string; kind: "RAR" | "ISO" | "OTHER"; label: string; detail: string; file: string; size: number; count: number; missing: number[]; busy: number[]; wasFreed?: boolean }

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
    const others = ofType(out, "archive_set") as unknown as OtherArchive[];
    const isos = ofType(out, "found_iso") as unknown as FoundIso[];
    setRows([
      ...sets.map((s) => ({ key: s.first, name: setName(s.first), kind: "RAR" as const, label: "RAR", file: basename(s.first), size: s.size, count: s.parts + s.missing.length, missing: s.missing, busy: s.busy ?? [],
        // more_after: the last part here says more follow, so the total is not known yet.
        detail: s.more_after ? `${s.parts} ${s.parts === 1 ? "part" : "parts"} so far, more to come` : s.missing.length ? `${s.parts} of ${s.parts + s.missing.length} parts` : `${s.parts} parts` })),
      ...others.map((o) => ({ key: o.first, name: setName(o.first), kind: "OTHER" as const, label: archiveFormat(o.first), file: basename(o.first), size: o.size,
        count: o.parts + o.missing.length, missing: o.missing, busy: o.busy ?? [],
        detail: o.missing.length ? `${o.parts} of ${o.parts + o.missing.length} parts` : o.parts > 1 ? `${o.parts} parts` : "single file" })),
      ...isos.map((i) => ({ key: i.path, name: setName(i.path), kind: "ISO" as const, label: "ISO", file: basename(i.path), size: i.size, count: 0, missing: [], busy: i.busy ? [1] : [], wasFreed: i.was_freed, detail: "ISO image" })),
    ]);
    setScannedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    setDisk(await diskSpace(folder));
  }, [folder]));

  useEffect(() => { scan.run(); }, [folder]); // eslint-disable-line react-hooks/exhaustive-deps
  // While a file is still being copied in, look again every few seconds so the row turns ready
  // on its own when the copy finishes.
  const copying = !!rows?.some((r) => r.busy.length);
  useEffect(() => {
    if (!copying) return;
    const h = setInterval(() => { if (!scan.busy) scan.run(); }, 4000);
    return () => clearInterval(h);
  }, [copying, scan.busy]); // eslint-disable-line react-hooks/exhaustive-deps
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
            <p className="soft" style={{ maxWidth: "52ch", marginBottom: 20 }}>EnhancedExtract lists every archive (RAR, ZIP, 7z, TAR and more) and game ISO in a folder, checks each one, and unpacks it. RAR sets give the space back as they go. Nothing is read until you pick one.</p>
            <div className="acts" style={{ justifyContent: "flex-start" }}>
              <button className="btn btn-primary" onClick={choose}>Choose folder</button>
              <span className="muted">or drop an archive or an .iso on the window · Ctrl+O</span>
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
            <span className="s">{busy ? <button className="btn sm" onClick={() => nav({ name: "jobs" })}>See jobs</button> : "nothing running"}</span></div>
          <div><span className="l">Need you</span><span className="v">{rows ? need : "…"}</span><span className="s">{need ? "missing or freed parts" : "every set complete"}</span></div>
          <div><span className="l">In this folder</span><span className="v"><Num value={total} format={gb} /><span className="unit">GB</span></span><span className="s">{rows ? `${rows.length} ${rows.length === 1 ? "set" : "sets"}` : " "}</span></div>
          <div><span className="l">Free on {drive(folder)}</span><span className="v">{disk ? <><Num value={disk.free} format={gb} /><span className="unit">GB</span></> : "—"}</span><span className="s">{disk ? `of ${gb(disk.total)} GB` : " "}</span></div>
        </div>
      </section>
      <SystemNotice />
      <section className="card bare" aria-labelledby="lib">
        <div className="ch"><h2 id="lib">Archives</h2><span className="meta">F5 rescans</span></div>
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

  if (!system || (system.unrar && system.sevenzip && system.winfsp && system.fusepy)) return null;
  const busy = check.busy || fuse.busy;
  // Missing extraction tools come first: they stop archives from opening at all.
  const tools = [!system.unrar && "UnRAR wasn't found, so RAR archives can't be opened. Install WinRAR.",
    !system.sevenzip && "7-Zip wasn't found, so zip, 7z, tar and similar archives can't be opened. Install 7-Zip."].filter(Boolean).join(" ");
  return (
    <>
      <div className="notice err" role="status">
        <span style={{ flex: 1 }}>{tools ? `${tools} Then check again.`
          : "ISO installs need the virtual drive: " + [!system.winfsp && "WinFsp isn't installed", !system.fusepy && "the fusepy package is missing"].filter(Boolean).join(" and ") + ". Extracting archives works."}
          {checkedAt && !busy && <span className="muted"> Still missing at {checkedAt}.</span>}</span>
        {system.unrar && system.sevenzip && !system.fusepy && (
          <button className="btn" onClick={() => fuse.run()} disabled={busy}><Busy busy={fuse.busy}>{fuse.busy ? "Installing fusepy" : "Install fusepy"}</Busy></button>
        )}
        <button className="btn" onClick={() => check.run()} disabled={busy}><Busy busy={check.busy}>{check.busy ? "Checking" : "Check again"}</Busy></button>
      </div>
      <ErrorNote error={fuse.error} onRetry={() => fuse.run()} />
    </>
  );
}

function SetTable({ rows, jobFor }: { rows: Row[] | null; jobFor: (p: string) => JobSnap | undefined }) {
  const { nav } = useApp();
  if (rows == null)
    return <div className="set-cards">{[0, 1, 2, 3].map((i) => <div key={i} className="lib-row set-card" style={{ height: 72 }}><span className="skel" style={{ width: "50%" }} /><span className="skel" style={{ width: "100%" }} /><span className="skel" /><span className="skel" /><span /></div>)}</div>;
  if (rows.length === 0)
    return <div className="empty">No archives or ISOs here (two folder levels deep). Choose another folder, or drop a file on the window.</div>;
  return (
    <>
      <div className="lib-row set-head small muted"><span>Archive</span><span>Parts</span><span style={{ textAlign: "right" }}>Packed</span><span>State</span><span /></div>
      <div className="set-cards stagger">
        {rows.map((r, ri) => {
          const job = jobFor(r.key);
          const pct = job?.progress?.overall;
          const [cls, text] = job ? ["neu live", `${r.kind === "ISO" ? "Installing" : job.progress?.phase === "verifying" ? "Verifying" : "Extracting"}${pct != null ? ` ${Math.floor(pct)}%` : ""}`]
            : r.missing.length ? ["neg", `Part ${partList(r.missing)} missing`]
            : r.busy.length ? ["warn", r.count > 1 ? `Part ${partList(r.busy)} still copying` : "Still copying"]
            : r.wasFreed ? ["warn", "Partly freed earlier"] : ["pos", "Ready"];
          // A file still being written can't be read yet: no way into the set until it's done.
          const wait = !job && !r.missing.length && r.busy.length > 0;
          const [label, go] = job ? ["Open", () => nav(jobRoute(job))]
            : r.missing.length ? ["Details", () => nav({ name: "rar", path: r.key })]
            : [r.kind === "ISO" ? "Install" : "Extract", () => nav(r.kind === "ISO" ? { name: "iso", path: r.key } : { name: "rar", path: r.key })];
          const multi = r.kind !== "ISO" && r.count > 1;
          const usedParts = job && multi && !job.progress?.whole ? Math.max(0, (job.progress?.part ?? 1) - 1) : 0;
          return (
            <div key={r.key} className={`lib-row set-card${wait ? " wait" : " row-link"}${job ? " live" : ""}`} style={{ height: 72, ["--i" as string]: ri }} onClick={wait ? undefined : go}>
              <div style={{ minWidth: 0 }}>
                <div className="set-name ellipsis">{r.name}</div>
                <div className="muted small ellipsis">{r.label} · {r.detail} · {r.file}</div>
              </div>
              {multi ? (
                <div className="tape mini" style={{ gap: r.count > 60 ? 1 : r.count > 30 ? 2 : 4 }} role="img" aria-label={r.missing.length ? `${r.count} parts, part ${r.missing.join(", ")} missing` : `${r.count} parts, all present`}>
                  {Array.from({ length: r.count }, (_, i) => i + 1).map((n) =>
                    <i key={n} style={{ ["--i" as string]: ri * 3 + n }} className={r.missing.includes(n) ? "missing" : r.busy.includes(n) ? "busy" : n <= usedParts ? "done" : ""} />)}
                </div>
              ) : <span className="muted small">{r.kind === "ISO" ? "single image" : "single file"}</span>}
              <span className="num" style={{ textAlign: "right", fontSize: 15 }}>{gb(r.size)}<span className="unit">GB</span></span>
              <span title={r.missing.length > 4 ? `Missing: part ${r.missing.join(", ")}` : undefined}><Status kind={cls}>{text}</Status></span>
              <span style={{ textAlign: "right" }}>
                <button className="btn" onClick={(e) => { e.stopPropagation(); go(); }} aria-label={`${label} ${r.name}`} disabled={wait}
                  title={wait ? "Still being copied. It can be opened once the copy finishes." : undefined}>{label}</button>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}

/** "2, 3, 4" stays as it is; a longer list keeps its first three and its last: "2, 3, 4, … 49". */
function partList(ns: number[]) {
  return ns.length <= 4 ? ns.join(", ") : `${ns.slice(0, 3).join(", ")}, … ${ns[ns.length - 1]}`;
}
