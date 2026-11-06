import { useCallback, useEffect, useRef, useState } from "react";
import { Num } from "../fx/motion";
import { Page, useApp } from "../App";
import { EXIT, EngineError, call, first, pickArchive, pickFolder, type Archive, type Space } from "../engine";
import { basename, drive, dur, gb, int, setName } from "../format";
import { useAction, useStored } from "../hooks";
import { Busy, ConfirmDelete, ErrorNote, PasswordDialog, SpaceCompare, Toggle, Warn } from "../components/ui";

export function RarSetup({ path }: { path?: string }) {
  const { nav, openPath, refreshJobs } = useApp();
  const [verify, setVerify] = useStored("ee.rar.verify", true);
  const [del, setDel] = useStored("ee.rar.delete", true);
  const [dest, setDest] = useState("");
  const [info, setInfo] = useState<Archive | null>(null);
  const [space, setSpace] = useState<{ del: Space; keep: Space } | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [pw, setPw] = useState<string | null>(null);
  const [askPw, setAskPw] = useState<"ask" | "wrong" | null>(null);
  const [confirm, setConfirm] = useState(false);
  // Delete mode: "safe" unless only "early" fits (picked once the engine has measured both).
  const [early, setEarly] = useState(false);
  const [resume, setResume] = useState(false);
  const pwArgs = (p: string | null) => (p ? ["--password-stdin"] : []);

  // Inspect twice (delete on and off) so both space figures are real engine numbers.
  const inspect = useCallback(async (destArg: string, password: string | null) => {
    if (!path) return;
    setLoadError(null);
    const base = ["rar", "inspect", path, ...(destArg ? ["--dest", destArg] : []), ...pwArgs(password)];
    try {
      const [a, b] = await Promise.all([call([...base, "--delete"], { stdin: password ?? undefined }), call(base, { stdin: password ?? undefined })]);
      setInfo(first(a, "archive") as unknown as Archive);
      const sd = first(a, "space") as unknown as Space, sk = first(b, "space") as unknown as Space;
      setSpace({ del: sd, keep: sk });
      // A stopped delete-mode run continues where it started; the engine says where.
      const resuming = !!a.result?.resume;
      setResume(resuming);
      if ((!destArg || resuming) && sd?.dest) setDest(sd.dest);
      setEarly(!!sd && (sd.needed_safe ?? sd.needed) > sd.free && !!sd.early_fits);
    } catch (e) {
      if (e instanceof EngineError && e.code === EXIT.PASSWORD) setAskPw(password ? "wrong" : "ask");
      else setLoadError(e);
    }
  }, [path]);

  useEffect(() => { inspect("", null); }, [inspect]);
  // Re-check space after the destination changes (it can be on another drive), debounced.
  const typed = useRef(false);
  useEffect(() => {
    if (!typed.current || !dest) return;
    const t = setTimeout(() => inspect(dest, pw), 500);
    return () => clearTimeout(t);
  }, [dest]); // eslint-disable-line react-hooks/exhaustive-deps

  const deleting = del || resume;
  const how = !deleting ? "keep" : early ? "early" : "safe";
  const cmd = (extra: string[]) => ["rar", "extract", path!, "--dest", dest, ...(deleting ? ["--delete"] : []), ...(how === "early" ? ["--early-delete"] : []),
    ...(verify ? [] : ["--no-verify"]), ...pwArgs(pw), ...extra];
  const start = useAction(async (confirmed: boolean) => {
    await call(cmd(["--dry-run"]), { stdin: pw ?? undefined });          // same checks as the real run, changes nothing
    if (how === "early" && !confirmed) { setConfirm(true); return; }    // only the risky mode asks again
    const out = await call(cmd(["--background", ...(deleting ? ["--yes"] : [])]), { stdin: pw ?? undefined });
    refreshJobs();
    nav({ name: "rarJob", id: out.result!.job });
  });
  const verifyOnly = useAction(async () => {
    const out = await call(["rar", "verify", path!, ...pwArgs(pw), "--background"], { stdin: pw ?? undefined });
    refreshJobs();
    nav({ name: "rarJob", id: out.result!.job });
  });

  if (!path)
    return (
      <Page title="Extract RAR" sub="Pick the first part of a set (.part1.rar). The other parts are found next to it.">
        <section className="card" style={{ maxWidth: 640 }}>
          <div className="ch"><h2>No set chosen</h2></div>
          <p className="soft" style={{ marginBottom: 16 }}>Or drop a .rar part on the window, or pick one in the Library.</p>
          <button className="btn btn-primary" onClick={async () => { const p = await pickArchive(); if (p) openPath(p); }}>Choose a .rar file</button>
        </section>
      </Page>
    );

  const name = setName(path);
  const free = space?.del.free ?? 0;
  const needs = space ? { safe: space.del.needed_safe ?? space.del.needed, early: space.del.needed_early ?? space.del.needed, keep: space.keep.needed } : null;
  const need = needs ? needs[how] : 0;
  const fits = needs ? need <= free : false;  const blocked = !info || !space || !dest || !fits;
  const why = !info ? "Reading the set…" : !fits ? "Not enough free space for this choice" : !dest ? "Choose where to extract" : undefined;
  const steps = [
    ...(verify ? [{ t: resume ? "Verify the parts left" : `Verify all ${info?.volumes.length ?? "…"} parts`, m: info ? `reads ${gb(info.packed)} GB` : "" }] : []),
    { t: <>Extract {info ? int(info.files) : "…"} files to <span className="mono">{dest || "…"}</span></>, m: info ? `writes ${gb(info.unpacked)} GB` : "" },
    ...(how === "safe" ? [{ t: "Delete each part once every file in it is out", m: info ? `frees ${gb(info.packed)} GB` : "" }] : []),
    ...(how === "early" ? [{ t: "Delete each part as soon as it's read", m: info ? `frees ${gb(info.packed)} GB` : "" }] : []),
  ];
  const rows = needs ? [
    { label: "Delete parts as their files finish", needed: needs.safe, chosen: how === "safe",
      note: space?.del.solid ? "Solid set: parts are deleted only once everything is out. If it stops, start it again to continue."
        : "Holds a file's parts until it's out. If it stops, start it again to continue where it left off." },
    { label: "Delete each part as soon as it's read", needed: needs.early, chosen: how === "early",
      note: "Needs the least space. If it stops or crashes, the file being extracted is lost." },
    ...(resume ? [] : [{ label: "Keep every part", needed: needs.keep, chosen: how === "keep", note: "Nothing is deleted; needs room for the whole game." }]),
  ] : [];

  return (
    <Page title={name} sub={info ? <>{info.volumes.length} parts{resume ? ", partly extracted" : ", all present"} · <span className="num">{gb(info.packed)}</span> GB {resume ? "left" : "packed"}, <span className="num">{gb(info.unpacked)}</span> GB unpacked · <span className="num">{int(info.files)}</span> files</>
      : loadError ? basename(path) : "Reading the set…"}
      actions={<>
        <button className="btn" onClick={() => verifyOnly.run()} disabled={!info || verifyOnly.busy}><Busy busy={verifyOnly.busy}>Verify only</Busy></button>
        <button className="btn btn-primary" onClick={() => start.run(false)} disabled={blocked || start.busy} title={why}><Busy busy={start.busy}>{resume ? "Resume" : "Start"}</Busy></button>
      </>}>
      <ErrorNote error={loadError} onRetry={() => inspect(dest, pw)} />
      <ErrorNote error={start.error || verifyOnly.error} />
      {resume && <div className="notice ok" role="status"><span>This set was partly extracted into <span className="mono">{dest}</span>. Resume skips the files already out and continues from the parts left.</span></div>}
      <section className="hero brand" aria-labelledby="sp">
        <div className="decision">
          <div>
            <h2 id="sp" style={{ marginBottom: 6 }}>Space on {drive(dest || path)}</h2>
            <div className="big-figure">{space ? <Num value={need} format={gb} /> : "…"}<span className="unit" style={{ fontSize: 20, color: "#3d3a06" }}>GB needed</span></div>
            <p className="small" style={{ fontWeight: 600, marginTop: 6 }}>{space ? <>of <span className="num">{gb(free)}</span> GB free{fits ? `, ${gb(free - need)} GB to spare` : ", not enough"}</> : "Working it out…"}</p>
          </div>
          <div>
            {space ? <SpaceCompare free={free} label="How to extract" rows={rows}
              onChoose={(i) => { const pick = rows[i]?.label; setDel(pick !== "Keep every part"); setEarly(pick === "Delete each part as soon as it's read"); }} /> : <p>Reading the set…</p>}
            {how === "early" && <div style={{ marginTop: 16 }}><Warn>If extraction stops or crashes, the file being extracted is lost and the parts already deleted can't be brought back. You'll confirm before it starts.</Warn></div>}
          </div>
        </div>
      </section>
      <div className="cols">
        <div className="stack">
          <section className="card" aria-labelledby="src">
            <div className="ch"><h2 id="src">Source and destination</h2></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <label className="lab">First part<input className="field" readOnly value={path} /></label>
              <label className="lab">Extract to
                <span className="join">
                  <input className="field" value={dest} readOnly={resume} title={resume ? "A resumed extraction continues in the folder it started in" : undefined}
                    onChange={(e) => { typed.current = true; setDest(e.target.value); }} spellCheck={false} />
                  <button className="btn" type="button" disabled={resume} onClick={async () => { const f = await pickFolder(dest || undefined); if (f) { typed.current = true; setDest(f); } }}>Browse</button>
                </span>
              </label>
              <div className="kv" style={{ borderTop: "1px solid var(--rule)", paddingTop: 12 }}>
                <span style={{ fontWeight: 500 }}>Password</span>
                {pw ? <span className="muted">Entered · <button className="tlink" onClick={() => setAskPw("ask")}>Change</button></span>
                  : <span className="muted">{info ? "Not needed, file names aren't encrypted" : "—"}</span>}
              </div>
            </div>
          </section>
        </div>
        <div className="stack">
          <section className="card" aria-labelledby="plan">
            <div className="ch"><h2 id="plan">What happens</h2>{info && <span className="meta">about {dur(estimate(info, verify))}</span>}</div>
            <Toggle label="Verify every part first" checked={verify} onChange={setVerify}
              desc="Reads every part and writes nothing, so a corrupt part stops the job before anything is deleted." />
            {deleting && !verify && <div style={{ margin: "4px 0 12px" }}><Warn>Verification is off: a corrupt part would only be found after earlier parts were deleted.</Warn></div>}
            <div className="rows" style={{ borderTop: "1px solid var(--rule)", marginTop: 4 }}>{steps.map((s, i) => <div key={i} className="kv" style={{ minHeight: 40 }}><span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{s.t}</span><span className="muted small" style={{ flex: "none" }}>{s.m}</span></div>)}</div>
          </section>
        </div>
      </div>

      {askPw && <PasswordDialog name={name} wrong={askPw === "wrong"} onClose={() => setAskPw(null)}
        onSubmit={(p) => { setAskPw(null); setPw(p); inspect(dest, p); }} />}
      {confirm && info && <ConfirmDelete title="Delete parts as soon as they're read?"
        body={<>There isn't room to keep a file's parts until it's out (that needs <span className="num">{gb(needs?.safe ?? 0)}</span> GB). Each of the <b className="num">{info.volumes.length}</b> parts of {name} is deleted as soon as it has been read instead. If extraction stops or crashes, the file being extracted is lost and its deleted parts must be downloaded again.</>}
        tick="I understand a stop can lose the file being extracted" confirm="Start and delete early"
        onClose={() => setConfirm(false)} onConfirm={() => { setConfirm(false); start.run(true); }} />}
    </Page>
  );
}

/** A rough time from sizes alone (about 150 MB/s read, 90 MB/s unpack); the running screen shows the real one. */
function estimate(info: Archive, verify: boolean) {
  return (verify ? info.packed / 150e6 : 0) + info.unpacked / 90e6;
}
