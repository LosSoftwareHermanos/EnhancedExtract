import { useEffect, useState } from "react";
import { Page, useApp } from "../App";
import { call, first, ofType, pickArchive, pickFolder, relaunchAsAdmin, type IsoInfo, type Space } from "../engine";
import { MiB, basename, drive, gb, int, setName } from "../format";
import { Busy, Check, ConfirmDelete, ErrorNote, SpaceCompare, Toggle, Warn } from "../components/ui";
import { useAction, useStored } from "../hooks";

interface Inspect { iso: IsoInfo; files: { path: string; size: number }[]; space: Space | null; windowsMounted: boolean; wasFreed: boolean }

export function IsoSetup({ path }: { path?: string }) {
  const { nav, openPath, system, refreshJobs } = useApp();
  const name = path ? setName(path) : "";
  const [dir, setDir] = useState(path ? `${drive(path)}\\Games\\${name}` : "");
  const [sizeMb, setSizeMb] = useState("");
  const [buffer, setBuffer] = useStored("ee.iso.buffer", 5);
  const [silent, setSilent] = useStored("ee.iso.silent", true);
  const [deleteIso, setDeleteIso] = useState(false);
  const [data, setData] = useState<Inspect | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState(false);
  const size = Math.round(Number(sizeMb.replace(/[,\s]/g, "")));
  const sizeOk = Number.isFinite(size) && size > 0;

  // Re-inspect as the size or buffer changes, debounced: the space figures come from the engine.
  useEffect(() => {
    if (!path) return;
    const t = setTimeout(async () => {
      try {
        const out = await call(["iso", "inspect", path, "--files", "--buffer-gb", String(buffer), ...(sizeOk ? ["--install-size-mb", String(size)] : [])]);
        setData({ iso: first(out, "iso") as unknown as IsoInfo, files: ofType(out, "file") as never, space: (first(out, "space") as unknown as Space) ?? null,
          windowsMounted: !!out.result?.windows_mounted, wasFreed: !!out.result?.was_freed });
        setLoadError(null);
      } catch (e) { setLoadError(e); }
    }, data ? 400 : 0);
    return () => clearTimeout(t);
  }, [path, size, buffer]); // eslint-disable-line react-hooks/exhaustive-deps

  const cmd = (extra: string[]) => ["iso", "install", path!, "--install-dir", dir, "--install-size-mb", String(size), "--buffer-gb", String(buffer),
    ...(silent ? ["--silent"] : []), ...(deleteIso ? ["--delete-iso"] : []), ...extra];
  const start = useAction(async (confirmed: boolean) => {
    await call(cmd(["--dry-run"]));
    if (!confirmed) { setConfirm(true); return; }
    const out = await call(cmd(["--background", "--yes"]));
    refreshJobs();
    nav({ name: "isoJob", id: out.result!.job });
  });

  if (!path)
    return (
      <Page title="Install from ISO" sub="Mounts a game ISO as a virtual drive and frees it while setup reads it, so you need far less free space.">
        <section className="card" style={{ maxWidth: 640 }}>
          <div className="ch"><h2>No ISO chosen</h2></div>
          <p className="soft" style={{ marginBottom: 16 }}>Or drop an .iso on the window, or pick one in the Library.</p>
          <button className="btn btn-primary" onClick={async () => { const p = await pickArchive(); if (p) openPath(p); }}>Choose an .iso file</button>
        </section>
      </Page>
    );

  const sysOk = system ? system.winfsp && system.fusepy : null;
  const big = (data?.files ?? []).filter((f) => data?.iso.freeable.includes(f.path));
  const rest = (data?.files ?? []).filter((f) => !data?.iso.freeable.includes(f.path));
  const space = data?.space;
  const why = !data ? "Reading the ISO…" : !data.iso.has_setup ? "There's no setup.exe in this ISO"
    : !sysOk ? "WinFsp isn't ready on this PC" : system && !system.admin ? "Needs administrator rights"
    : data.windowsMounted ? "Windows has this ISO mounted: eject it first" : !dir ? "Choose an install folder"
    : !sizeOk ? "Enter the install size from setup" : space && !space.enough ? "Not enough free space" : undefined;

  return (
    <Page title={name} sub={data ? <><span className="mono">{basename(path)}</span> · <span className="num">{gb(data.iso.size)}</span> GB · <span className="num">{int(data.iso.files)}</span> files · {data.iso.freeable.length} large .bin files can be freed while setup reads them</> : "Reading the ISO…"}
      actions={<>
        <button className="btn btn-primary" onClick={() => start.run(false)} disabled={!!why || start.busy} title={why}><Busy busy={start.busy}>Mount and install</Busy></button>
      </>}>
      <ErrorNote error={loadError} />
      <ErrorNote error={start.error} />
      {why && data && <p className="muted" role="status">Mount and install is off: {why.toLowerCase()}.</p>}
      <div className="cols">
        <div className="stack">
          <section className="card" aria-labelledby="ins">
            <div className="ch"><h2 id="ins">Install</h2></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <label className="lab">Install folder
                <span className="join"><input className="field" value={dir} onChange={(e) => setDir(e.target.value)} spellCheck={false} />
                  <button className="btn" type="button" onClick={async () => { const f = await pickFolder(dir || undefined); if (f) setDir(f); }}>Browse</button></span>
                {dir && drive(dir) !== drive(path) && <span className="hint" style={{ color: "var(--warning)" }}>Different drive from the ISO: freeing the ISO won't make room on {drive(dir)}</span>}
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <label className="lab">Install size
                  <span className="join"><input className="field" inputMode="numeric" style={{ textAlign: "right" }} value={sizeMb} placeholder="52,000"
                    onChange={(e) => setSizeMb(e.target.value)} aria-invalid={!!sizeMb && !sizeOk} aria-describedby="size-hint" /><span className="muted">MB</span></span>
                  <span className="hint" id="size-hint">From setup's "free disk space required"</span>
                </label>
                <label className="lab"><span style={{ display: "flex", justifyContent: "space-between" }}>Safety buffer<span className="num" style={{ fontWeight: 400 }}>{buffer} GB</span></span>
                  <input type="range" min={1} max={20} value={buffer} onChange={(e) => setBuffer(Number(e.target.value))} aria-describedby="buf-hint" />
                  <span className="hint" id="buf-hint">Kept behind setup in case it reads back</span>
                </label>
              </div>
              <div>
                <Toggle label="Run setup silently" checked={silent} onChange={setSilent} desc="No setup windows. Installs straight into the folder above." />
                <Toggle label="Delete the ISO after a clean install" checked={deleteIso} onChange={setDeleteIso} desc="Only after exit code 0, a clean setup log and every .bin read to the end." />
              </div>
            </div>
          </section>
          <section className="card" aria-labelledby="chk">
            <div className="ch"><h2 id="chk">Before mounting</h2></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 24 }}>
              <Check ok={sysOk} label="WinFsp driver" value={system && !system.fusepy ? "fusepy missing" : undefined} />
              <Check ok={system?.admin ?? null} label="Administrator" value={system?.admin ? "yes" : undefined}
                action={system && !system.admin ? <button className="tlink" onClick={() => relaunchAsAdmin()}>Restart as admin</button> : undefined} />
              <Check ok={data ? !data.windowsMounted : null} label="Not mounted by Windows" />
              <Check ok={data ? data.iso.has_setup : null} label="setup.exe in the root" value={data?.iso.has_setup ? "found" : undefined} />
            </div>
          </section>
        </div>
        <div className="stack">
          <section className="card" aria-labelledby="sp">
            <div className="ch"><h2 id="sp">Space on {drive(path)}</h2><span className="meta">{space ? <><span className="num">{gb(space.free)}</span> GB free now</> : sizeOk ? "…" : "enter the install size"}</span></div>
            {space ? <SpaceCompare free={space.free} rows={[
              { label: "Install while freeing", needed: space.needed, chosen: true, note: `${buffer} GB buffer + 2 GB margin${space.growth ? ` + ${gb(space.growth)} GB game bigger than the ISO` : ""}` },
              { label: "Normal install, ISO kept", needed: size * MiB, chosen: false },
            ]} /> : <p className="muted">The install size decides how much space this needs.</p>}
            <div style={{ marginTop: 16 }}><Warn>The ISO is freed while setup reads it. If setup fails or the PC crashes, the ISO is gone: keep a copy or be ready to download it again.</Warn></div>
            {data?.wasFreed && <div style={{ marginTop: 12 }}><Warn>This ISO was already partly freed in an earlier run; those parts are gone.</Warn></div>}
          </section>
          <section className="card" aria-labelledby="fl">
            <div className="ch"><h2 id="fl">In the ISO</h2><span className="meta">{data ? `${int(data.iso.files)} files` : "…"}</span></div>
            <div className="small muted" style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 96px 72px", paddingBottom: 6 }}><span>File</span><span style={{ textAlign: "right" }}>Size</span><span style={{ textAlign: "right" }}>Freed</span></div>
            <div className="rows">
              {big.map((f) => <FileRow key={f.path} name={f.path.replace(/^\//, "")} size={f.size} freed />)}
              {rest.length > 0 && <FileRow name={`${rest.length} other ${rest.length === 1 ? "file" : "files"}`} size={rest.reduce((a, f) => a + f.size, 0)} freed={false} />}
            </div>
          </section>
        </div>
      </div>
      {confirm && <ConfirmDelete title={`Install ${name} while freeing the ISO?`}
        body={<>The ISO (<span className="num">{gb(data?.iso.size ?? 0)}</span> GB) is deleted piece by piece as setup reads it, keeping the last {buffer} GB. If setup fails, is cancelled or the PC crashes, the ISO is lost.{deleteIso ? " After a clean install the rest of it is deleted too." : ""}</>}
        tick="I understand the ISO can't be recovered" confirm="Mount and install"
        onClose={() => setConfirm(false)} onConfirm={() => { setConfirm(false); start.run(true); }} />}
    </Page>
  );
}

function FileRow({ name, size, freed }: { name: string; size: number; freed: boolean }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 96px 72px", alignItems: "center", height: 36 }}>
      <span className="mono ellipsis">{name}</span>
      <span className="num" style={{ textAlign: "right" }}>{gb(size)}<span className="muted"> GB</span></span>
      <span style={{ textAlign: "right" }} className={freed ? "" : "muted"}>{freed ? "yes" : "kept"}</span>
    </div>
  );
}
