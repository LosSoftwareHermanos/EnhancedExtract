import { useEffect, useRef, useState, type ReactNode } from "react";
import { EngineError } from "../engine";
import { scaled, size, unitFor } from "../format";
import { isMuted, lengthMs, play, toggleMuted, useMuted } from "../sound";
import { inTauri } from "../engine";
import { Decode } from "../fx/motion";

const PATHS: Record<string, string> = {
  library: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  extract: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
  disc: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
  jobs: '<path d="M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  system: '<path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z"/>',
  warn: '<path d="M12 3 2 21h20z"/><path d="M12 10v5M12 18v.5"/>',
  fx: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5"/>',
  fxoff: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M4 4l16 16"/>',
};
export function Icon({ name }: { name: keyof typeof PATHS | string }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{ __html: PATHS[name] ?? "" }} />;
}

export function Toggle({ label, desc, checked, onChange, disabled }: { label: string; desc?: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="sw" onClick={() => !disabled && onChange(!checked)}>
      <div><b>{label}</b>{desc && <span className="d">{desc}</span>}</div>
      <button type="button" className="tog" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
        onClick={(e) => { e.stopPropagation(); onChange(!checked); }} />
    </div>
  );
}

/** Inline error inside the block that failed: what happened, and the engine's fix when it has one. */
export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const e = error instanceof EngineError ? error : new EngineError(-1, String(error));
  return (
    <div className="notice err" role="alert">
      <Icon name="warn" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div>{e.message}</div>
        {e.fix && <div className="fix">{e.fix}</div>}
      </div>
      {onRetry && <button className="btn btn-danger" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Warn({ children }: { children: ReactNode }) {
  return <div className="notice"><Icon name="warn" /><span>{children}</span></div>;
}

/** A state label: an icon for the kind of state, then the text in brackets, like [Ready].
 *  kind: pos (ready, done), neg (missing, failed), warn, neu (stopped), "neu live" (running). */
export function Status({ kind, children }: { kind: string; children: ReactNode }) {
  return <span className={`pill ${kind}`}><i aria-hidden="true" /><span>[{children}]</span></span>;
}

export function Busy({ busy, children }: { busy: boolean; children: ReactNode }) {
  return <>{busy && <span className="spin" aria-hidden="true" />}{children}</>;
}

/** Modal dialog: focus moves in (to the safe choice), Tab stays inside, Esc cancels, focus returns after. */
/** How a job ended: a green or red frame that wipes in with a flicker, an icon in the left corner
 *  that draws itself and keeps a slow glow, and a decoding title. `fresh` (the job ended while on
 *  screen) also plays the result sound. */
export function Outcome({ ok, title, children, actions, fresh }: { ok: boolean; title: string; children?: ReactNode; actions?: ReactNode; fresh?: boolean }) {
  useEffect(() => { if (fresh) play(ok ? "job_ok" : "job_failed"); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className={`outcome ${ok ? "ok" : "bad"}`} role={ok ? "status" : "alert"}>
      <span className="oc-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24">{ok ? <path d="M5 12.5l4.5 4.5L19 7.5" /> : <path d="M6.5 6.5l11 11M6.5 17.5l11-11" />}</svg>
      </span>
      <div className="oc-body">
        <Decode className="oc-title" text={title} />
        {children && <div className="oc-text">{children}</div>}
      </div>
      {actions && <div className="oc-actions">{actions}</div>}
    </div>
  );
}

/** A password was accepted: the result-card look (green frame, a tick that draws itself in,
 *  a decoding title), centred over the page for about a second. Click skips it. */
export function PasswordMatch({ name, onDone }: { name: string; onDone: () => void }) {
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    play("access_granted");
    const t = setTimeout(() => done.current(), 1250);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="scrim match-scrim" onClick={() => done.current()}>
      <div className="outcome ok match" role="status">
        <span className="oc-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
        <div className="oc-body">
          <Decode className="oc-title" text="Password match" />
          <div className="oc-text">{name} is unlocked.</div>
        </div>
      </div>
    </div>
  );
}

/** Not used for now (kept for later): the louder version. The password worked: a green frame wipes in, a padlock draws itself open, "ACCESS GRANTED"
 *  decodes with a glitch, a bar fills, and the whole thing fades (about 1.4 s, click skips). */
export function AccessGranted({ onDone }: { onDone: () => void }) {
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    play("access_granted");
    const t = setTimeout(() => done.current(), 1450);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="scrim granted-scrim" onClick={() => done.current()}>
      <div className="granted" role="status">
        <svg className="granted-icon" viewBox="0 0 48 48" aria-hidden="true">
          <path className="g-body" d="M11 22h26v19H11z" />
          <path className="g-shackle" d="M16 22v-7a8 8 0 0 1 15.5-2.8" />
          <path className="g-key" d="M24 29v5" />
        </svg>
        <Decode className="granted-title" text="Access granted" />
        <span className="granted-sub">Password accepted · set unlocked</span>
        <span className="granted-bar"><i /></span>
      </div>
    </div>
  );
}

/** Sound on/off, minimize and EXIT, as cut buttons: the right end of every window's title bar.
 *  EXIT hides the window at once and closes it once its sound has played. */
export function WindowControls() {
  const muted = useMuted();
  const win = async (op: "minimize" | "close") => {
    if (!inTauri) return;
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const w = getCurrentWindow();
    if (op === "minimize") return w.minimize();
    await w.hide();
    setTimeout(() => void w.close(), isMuted() ? 0 : lengthMs("exit") + 150);
  };
  return (
    <div className="win">
      <button className={`btn${muted ? " btn-danger" : ""}`} data-sound="none" aria-pressed={!muted} aria-label={muted ? "Sound off" : "Sound on"}
        title={muted ? "Sound off: click to turn it on" : "Sound on: click to turn it off"} onClick={toggleMuted}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 6h3l4-3v10l-4-3H2z" />{muted ? <path d="M11 6l4 4M15 6l-4 4" /> : <path d="M11.5 5.5a3.5 3.5 0 0 1 0 5M13.5 3.5a6 6 0 0 1 0 9" />}</svg>
      </button>
      <button className="btn" data-sound="minimize" aria-label="Minimize" onClick={() => win("minimize")}>—</button>
      <button className="btn btn-danger" data-sound="exit" aria-label="Exit. Running jobs keep going." title="Exit. Running jobs keep going." onClick={() => win("close")}>Exit</button>
    </div>
  );
}

export function Dialog({ title, children, actions, onClose, className }: { title: string; children: ReactNode; actions: ReactNode; onClose: () => void; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => play("popup"), []);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const box = ref.current!;
    const focusables = () => [...box.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), [href]")];
    (box.querySelector<HTMLElement>("[data-autofocus]") ?? focusables()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      if (e.key === "Tab") {
        const f = focusables(); if (!f.length) return;
        const [a, z] = [f[0], f[f.length - 1]];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
        else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); before?.focus?.(); };
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`dialog${className ? ` ${className}` : ""}`} role="dialog" aria-modal="true" aria-labelledby="dlg-title" ref={ref}>
        <h2 id="dlg-title">{title}</h2>
        {children}
        <div className="actions">{actions}</div>
      </div>
    </div>
  );
}

/** Confirmation for steps that delete data: names what goes, and needs an explicit tick. */
export function ConfirmDelete({ title, body, tick, confirm, onConfirm, onClose }: { title: string; body: ReactNode; tick: string; confirm: string; onConfirm: () => void; onClose: () => void }) {
  const [ok, setOk] = useState(false);
  return (
    <Dialog title={title} onClose={onClose} actions={<>
      <button className="btn" data-autofocus onClick={onClose}>Cancel</button>
      <button className="btn btn-danger solid" disabled={!ok} onClick={onConfirm} title={ok ? undefined : "Tick the box first"}>{confirm}</button>
    </>}>
      <p className="soft">{body}</p>
      <label style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 500, cursor: "pointer" }}>
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />{tick}
      </label>
    </Dialog>
  );
}

export function PasswordDialog({ name, wrong, onSubmit, onClose }: { name: string; wrong: boolean; onSubmit: (pw: string) => void; onClose: () => void }) {
  const [pw, setPw] = useState("");
  const [show, setShow] = useState(false);
  return (
    <Dialog title={`${name} is locked`} onClose={onClose} actions={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn btn-primary" disabled={!pw} onClick={() => onSubmit(pw)}>Open it</button>
    </>}>
      <p className="soft">This set is password protected. Enter its password to open it.</p>
      <form className="lab" onSubmit={(e) => { e.preventDefault(); if (pw) onSubmit(pw); }}>
        <label htmlFor="pw">Password</label>
        <span className="join">
          <input id="pw" data-autofocus className="field" type={show ? "text" : "password"} value={pw} autoComplete="off"
            onChange={(e) => setPw(e.target.value)} aria-invalid={wrong} aria-describedby={wrong ? "pw-err" : undefined} />
          <button type="button" className="btn" onClick={() => setShow(!show)} aria-pressed={show}>{show ? "Hide" : "Show"}</button>
        </span>
        {wrong && <span id="pw-err" className="small" style={{ color: "var(--negative)", fontWeight: 400 }}>That password didn't open it. Passwords are case-sensitive.</span>}
      </form>
    </Dialog>
  );
}

/** Two bars on one scale (the drive's free space): what this plan needs against the alternative. */
/** With `onChoose`, the rows are the choice itself (a radio group): pick a plan by its space. */
export function SpaceCompare({ free, rows, onChoose, label }: { free: number; rows: { label: string; needed: number; chosen: boolean; note?: ReactNode }[]; onChoose?: (i: number) => void; label?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: onChoose ? 6 : 16 }} role={onChoose ? "radiogroup" : undefined} aria-label={label}>
      {rows.map((r, i) => {
        const pct = Math.min(100, (r.needed / Math.max(free, 1)) * 100);
        const over = r.needed > free;
        const Tag = onChoose ? "button" : "div";
        return (
          <Tag className={`cmp${onChoose ? " choice" : ""}`} key={r.label} {...(onChoose ? { type: "button" as const, role: "radio", "aria-checked": r.chosen, onClick: () => onChoose(i) } : {})}>
            <div className="top2"><span className={r.chosen ? "" : "soft"}>{onChoose && <span className="radio" aria-hidden="true" />}{r.label}</span>
              <span className="num">{scaled(r.needed, unitFor(r.needed))}<span className="muted"> {unitFor(r.needed)} needed</span></span></div>
            <div className="cmpbar" role="img" aria-label={`${r.label}: needs ${size(r.needed)}, ${size(free)} free`}>
              <span data-chosen={over ? undefined : String(r.chosen)} style={{ width: `${pct}%`, background: over ? "var(--negative)" : r.chosen ? "var(--accent)" : "var(--control)" }} />
            </div>
            {over ? <span className="small" style={{ color: "var(--negative)" }}>Doesn't fit: <span className="num">{scaled(r.needed - free, unitFor(r.needed - free))}</span> {unitFor(r.needed - free)} short</span>
              : r.note && <span className="small muted">{r.note}</span>}
          </Tag>
        );
      })}
    </div>
  );
}

export function Check({ ok, label, value, action }: { ok: boolean | null; label: string; value?: ReactNode; action?: ReactNode }) {
  const color = ok == null ? "var(--control)" : ok ? "var(--positive)" : "var(--negative)";
  return (
    <div className="kv">
      <span><span className="dot" style={{ background: color }} />{label}</span>
      {action ?? <span className="muted num">{value ?? (ok == null ? "…" : ok ? "ok" : "missing")}</span>}
    </div>
  );
}

export type Option = { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; needed?: number; figure?: ReactNode; note: ReactNode };

/** Checkbox rows in the same look as the space rows: label, figure, a bar for the space an
 *  option needs against what's free, and a note. */
export function Options({ free, label, options }: { free: number; label: string; options: Option[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }} role="group" aria-label={label}>
      {options.map((o) => {
        const over = o.needed != null && o.checked && o.needed > free;
        const pct = o.needed != null ? Math.min(100, (o.needed / Math.max(free, 1)) * 100) : 0;
        return (
          <button type="button" key={o.label} className="cmp choice" role="checkbox" aria-checked={o.checked} disabled={o.disabled}
            onClick={() => o.onChange(!o.checked)}>
            <div className="top2"><span className={o.checked ? "" : "soft"}><span className="box" aria-hidden="true" />{o.label}</span>
              {o.needed != null ? <span className="num">{scaled(o.needed, unitFor(o.needed))}<span className="muted"> {unitFor(o.needed)} needed</span></span>
                : o.figure && <span className="num">{o.figure}</span>}</div>
            {o.needed != null && <div className="cmpbar" role="img" aria-label={`needs ${size(o.needed)}, ${size(free)} free`}>
              <span style={{ width: `${pct}%`, background: over ? "var(--negative)" : o.checked ? "var(--accent)" : "var(--control)" }} /></div>}
            {over ? <span className="small" style={{ color: "var(--negative)" }}>Doesn't fit: <span className="num">{size(o.needed! - free)}</span> short</span>
              : <span className="small muted">{o.note}</span>}
          </button>
        );
      })}
    </div>
  );
}
