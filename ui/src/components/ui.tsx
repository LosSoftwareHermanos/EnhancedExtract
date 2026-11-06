import { useEffect, useRef, useState, type ReactNode } from "react";
import { EngineError } from "../engine";
import { scaled, size, unitFor } from "../format";

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
      {onRetry && <button className="tlink" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Warn({ children }: { children: ReactNode }) {
  return <div className="notice"><Icon name="warn" /><span>{children}</span></div>;
}

export function Busy({ busy, children }: { busy: boolean; children: ReactNode }) {
  return <>{busy && <span className="spin" aria-hidden="true" />}{children}</>;
}

/** Modal dialog: focus moves in (to the safe choice), Tab stays inside, Esc cancels, focus returns after. */
export function Dialog({ title, children, actions, onClose }: { title: string; children: ReactNode; actions: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
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
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" ref={ref}>
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
      <p className="soft">This set has encrypted file names. Enter its password to see what's inside.</p>
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
