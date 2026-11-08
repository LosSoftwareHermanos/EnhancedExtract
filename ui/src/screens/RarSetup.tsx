import { useCallback, useEffect, useRef, useState } from "react";
import { Num } from "../fx/motion";
import { Page, useApp } from "../App";
import { EXIT, EngineError, call, first, pickArchive, pickFolder, type Archive, type Space } from "../engine";
import { archiveFormat, basename, drive, dur, int, scaled, setName, size, unitFor } from "../format";
import { useAction, useStored } from "../hooks";
import { Busy, ErrorNote, Options, PasswordDialog, PasswordMatch, Warn, type Option } from "../components/ui";

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
  const [resume, setResume] = useState(false);
  // After a password is accepted: "granted" shows the pop-up over a hidden page, "reveal" then
  // brings the page in panel by panel.
  const [unlock, setUnlock] = useState<"" | "granted" | "reveal">("");
  const fx = () => unlock === "granted" ? "pre-reveal" : unlock === "reveal" ? "reveal-in" : "";
  const pwArgs = (p: string | null) => (p ? ["--password-stdin"] : []);

  // Inspect twice (delete on and off) so both space figures are real engine numbers.
  const inspect = useCallback(async (destArg: string, password: string | null) => {
    if (!path) return;
    setLoadError(null);
    const base = ["archive", "inspect", path, ...(destArg ? ["--dest", destArg] : []), ...pwArgs(password)];
    try {
      const [a, b] = await Promise.all([call([...base, "--delete"], { stdin: password ?? undefined }), call(base, { stdin: password ?? undefined })]);
      setInfo(first(a, "archive") as unknown as Archive);
      const sd = first(a, "space") as unknown as Space, sk = first(b, "space") as unknown as Space;
      setSpace({ del: sd, keep: sk });
      // A stopped delete-mode run continues where it started; the engine says where.
      const resuming = !!a.result?.resume;
      setResume(resuming);
      if ((!destArg || resuming) && sd?.dest) setDest(sd.dest);
      return true;
    } catch (e) {
      if (e instanceof EngineError && e.code === EXIT.PASSWORD) setAskPw(password ? "wrong" : "ask");
      else setLoadError(e);
      return false;
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
  // Archives that are not RAR can't be freed while they are read: the whole archive goes once it is out.
  const generic = !!space?.del.generic;
  // Deleting works like the first version: each part goes as soon as UnRAR moves on to the next
  // one, so a set holding one big file needs about one part of room instead of the whole game.
  const how = !deleting ? "keep" : generic ? "after" : "early";
  const cmd = (extra: string[]) => ["archive", "extract", path!, "--dest", dest, ...(deleting ? ["--delete"] : []), ...(how === "early" ? ["--early-delete"] : []),
    ...(verify ? [] : ["--no-verify"]), ...pwArgs(pw), ...extra];
  const start = useAction(async () => {
    await call(cmd(["--dry-run"]), { stdin: pw ?? undefined });          // same checks as the real run, changes nothing
    const out = await call(cmd(["--background", ...(deleting ? ["--yes"] : [])]), { stdin: pw ?? undefined });
    refreshJobs();
    nav({ name: "rarJob", id: out.result!.job });
  });
  const verifyOnly = useAction(async () => {
    const out = await call(["archive", "verify", path!, ...pwArgs(pw), "--background"], { stdin: pw ?? undefined });
    refreshJobs();
    nav({ name: "rarJob", id: out.result!.job });
  });

  if (!path)
    return (
      <Page title="Extract" sub="Pick an archive: RAR, ZIP, 7z, TAR and more. For a split set pick its first part (.part1.rar, .7z.001); the other parts are found next to it.">
        <section className="card" style={{ maxWidth: 640 }}>
          <div className="ch"><h2>No set chosen</h2></div>
          <p className="soft" style={{ marginBottom: 16 }}>Or drop an archive on the window, or pick one in the Library.</p>
          <button className="btn btn-primary" onClick={async () => { const p = await pickArchive(); if (p) openPath(p); }}>Choose an archive</button>
        </section>
      </Page>
    );

  const name = setName(path);
  const free = space?.del.free ?? 0;
  const needs = space ? { safe: space.del.needed_safe ?? space.del.needed, early: space.del.needed_early ?? space.del.needed,
    keep: space.keep.needed, after: space.del.needed } : null;
  const need = needs ? needs[how] : 0;
  const fits = needs ? need <= free : false;  const blocked = !info || !space || !dest || !fits;
  const why = !info ? "Reading the set…" : !fits ? "Not enough free space for this choice" : !dest ? "Choose where to extract" : undefined;
  const parts = info?.volumes.length ?? 0;
  const files = info ? (info.files ? `${int(info.files)} files` : "the files") : "…";
  const steps = [
    ...(verify ? [{ t: generic ? "Verify the archive" : resume ? "Verify the parts left" : `Verify all ${info?.volumes.length ?? "…"} parts`, m: info ? `reads ${size(info.packed)}` : "" }] : []),
    { t: <>Extract {files} to <span className="mono">{dest || "…"}</span></>, m: info ? `writes ${size(info.unpacked)}` : "" },
    ...(how === "early" ? [{ t: "Delete each part as soon as it has been extracted", m: info ? `frees ${size(info.packed)}` : "" }] : []),
    ...(how === "after" ? [{ t: parts > 1 ? `Delete all ${parts} parts once everything is out cleanly` : "Delete the archive once everything is out cleanly", m: info ? `frees ${size(info.packed)}` : "" }] : []),
  ];
  // The two options of the first version, drawn as rows: verify, and delete (with what it needs).
  const delNeed = needs ? (generic ? needs.after : needs.early) : 0;
  const options: Option[] = [
    { label: generic ? "Verify the archive before extracting (recommended)" : "Verify all parts before extracting (recommended)", checked: verify, onChange: setVerify,
      figure: info ? <>{scaled(info.packed, unitFor(info.packed))}<span className="muted"> {unitFor(info.packed)} read</span></> : null,
      note: "Reads everything and writes nothing, so a corrupt part stops the job before anything is deleted." },
    { label: generic ? (parts > 1 ? "Delete the parts once everything is out cleanly" : "Delete the archive once everything is out cleanly")
        : "Delete each part as soon as it has been extracted",
      checked: deleting, onChange: setDel, disabled: resume, needed: delNeed,
      note: generic ? "A non-RAR archive can't be freed while it's read, so this frees its space only at the end. Nothing is deleted if anything goes wrong."
        : <>Needs <span className="num">{size(delNeed)}</span> instead of <span className="num">{size(needs?.keep ?? 0)}</span>. If extraction stops or crashes, the file being extracted is lost and its deleted parts must be downloaded again.</> },
  ];

  return (
    <Page title={name} sub={info ? <>{generic ? <>{archiveFormat(path)}{parts > 1 ? `, ${parts} parts, all present` : ""}</> : <>{info.volumes.length} parts{resume ? ", partly extracted" : ", all present"}</>} · <span className="num">{size(info.packed)}</span> {resume ? "left" : "packed"}, <span className="num">{size(info.unpacked)}</span> unpacked{info.files ? <> · <span className="num">{int(info.files)}</span> files</> : null}</>
      : loadError ? basename(path) : "Reading the archive…"}
      actions={<>
        <button className="btn" onClick={() => verifyOnly.run()} disabled={!info || verifyOnly.busy}><Busy busy={verifyOnly.busy}>Verify only</Busy></button>
        <button className="btn btn-primary" onClick={() => start.run()} disabled={blocked || start.busy} title={why}><Busy busy={start.busy}>{resume ? "Resume" : "Start"}</Busy></button>
      </>}>
      <ErrorNote error={loadError} onRetry={() => inspect(dest, pw)} />
      <ErrorNote error={start.error || verifyOnly.error} />
      {resume && <div className="notice ok" role="status"><span>This set was partly extracted into <span className="mono">{dest}</span>. Resume skips the files already out and continues from the parts left.</span></div>}
      <section className={`hero brand ${fx()}`} style={{ ["--r" as string]: 0 }} aria-labelledby="sp">
        <div className="decision">
          <div>
            <h2 id="sp" style={{ marginBottom: 6 }}>Space on {drive(dest || path)}</h2>
            <div className="big-figure">{space ? <Num value={need} format={(n) => scaled(n, unitFor(need))} /> : "…"}<span className="unit" style={{ fontSize: 20 }}>{space ? unitFor(need) : "GB"} needed</span></div>
            <p className="small" style={{ fontWeight: 600, marginTop: 6 }}>{space ? <>of <span className="num">{size(free)}</span> free{fits ? `, ${size(free - need)} to spare` : ", not enough"}</> : "Working it out…"}</p>
          </div>
          <div>
            {space ? <Options free={free} label="How to extract" options={options} /> : <p>Reading the set…</p>}
            {deleting && !verify && <div style={{ marginTop: 12 }}><Warn>{generic ? "Verification is off: extraction still stops on any error, and nothing is deleted unless it finishes cleanly." : "Verification is off: a corrupt part would only be found after earlier parts were deleted."}</Warn></div>}
          </div>
        </div>
      </section>
      <div className={`cols ${fx()}`} style={{ ["--r" as string]: 1 }}>
        <div className="stack">
          <section className="card" aria-labelledby="src">
            <div className="ch"><h2 id="src">Source and destination</h2></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <label className="lab">{generic ? "Archive" : "First part"}<input className="field" readOnly value={path} /></label>
              <label className="lab">Extract to
                <span className="join">
                  <input className="field" value={dest} readOnly={resume} title={resume ? "A resumed extraction continues in the folder it started in" : undefined}
                    onChange={(e) => { typed.current = true; setDest(e.target.value); }} spellCheck={false} />
                  <button className="btn" type="button" disabled={resume} onClick={async () => { const f = await pickFolder(dest || undefined); if (f) { typed.current = true; setDest(f); } }}>Browse</button>
                </span>
              </label>
              <div className="kv" style={{ borderTop: "1px solid var(--rule)", paddingTop: 12 }}>
                <span style={{ fontWeight: 500 }}>Password</span>
                {pw ? <span className="muted">Entered · <button className="btn sm" onClick={() => setAskPw("ask")}>Change</button></span>
                  : <span className="muted">{info ? "Not needed" : "—"}</span>}
              </div>
            </div>
          </section>
        </div>
        <div className="stack">
          <section className="card" aria-labelledby="plan">
            <div className="ch"><h2 id="plan">What happens</h2>{info && <span className="meta">about {dur(estimate(info, verify))}</span>}</div>
            <div className="rows">{steps.map((s, i) => <div key={i} className="kv" style={{ minHeight: 40 }}><span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{s.t}</span><span className="muted small" style={{ flex: "none" }}>{s.m}</span></div>)}</div>
          </section>
        </div>
      </div>

      {askPw && <PasswordDialog name={name} wrong={askPw === "wrong"} onClose={() => setAskPw(null)}
        onSubmit={async (p) => { setAskPw(null); setPw(p); if (await inspect(dest, p)) setUnlock("granted"); }} />}
      {/* "reveal" stays once set: dropping the class would hand the panels back to the normal
          screen-enter animation (the left-to-right wipe) and play it a second time. */}
      {unlock === "granted" && <PasswordMatch name={name} onDone={() => setUnlock("reveal")} />}
    </Page>
  );
}

/** A rough time from sizes alone (about 150 MB/s read, 90 MB/s unpack); the running screen shows the real one. */
function estimate(info: Archive, verify: boolean) {
  return (verify ? info.packed / 150e6 : 0) + info.unpacked / 90e6;
}
