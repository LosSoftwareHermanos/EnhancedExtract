import { useMemo, useState } from "react";
import { Page, jobRoute, useApp } from "../App";
import { type Ev, type JobSnap, jobLogs } from "../engine";
import { dur, gb, jobStarted, setName, shortId } from "../format";
import { usePoll } from "../hooks";
import { ErrorNote } from "../components/ui";

type Tab = "all" | "running" | "done" | "failed";
const KIND: Record<string, string> = { "rar extract": "Extract", "rar verify": "Verify", "archive extract": "Extract", "archive verify": "Verify", "iso install": "Install", "iso delete": "Delete ISO", "system install-winfsp": "Install WinFsp" };
const PROBLEMS = ["warning", "error"];

export function Jobs({ initial }: { initial?: string }) {
  const { jobs, nav } = useApp();
  const [tab, setTab] = useState<Tab>("all");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<string | undefined>(initial);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const list = jobs ?? [];
  const counts = { all: list.length, running: 0, done: 0, failed: 0 } as Record<Tab, number>;
  for (const j of list) counts[j.state === "died" ? "failed" : (j.state as Tab)]++;
  const shown = useMemo(() => list.filter((j) => (tab === "all" || (tab === "failed" ? j.state === "failed" || j.state === "died" : j.state === tab))
    && (!q || j.command.toLowerCase().includes(q.toLowerCase()))), [list, tab, q]);
  const selected = list.find((j) => j.id === sel) ?? shown[0];
  const logs = usePoll(() => (selected ? jobLogs(selected.id, 60, problemsOnly ? PROBLEMS : undefined) : Promise.resolve([])), selected?.state === "running" ? 2000 : 15000, !!selected);
  const failed = list.find((j) => j.state === "failed" || j.state === "died");

  return (
    <Page title="Jobs"
      sub={jobs == null ? "Loading…" : <>{counts.running} running.{failed && failed.job_exit_code !== 130 && <> {setName(failed.argv?.[2] ?? "")} failed at {jobStarted(failed.id)}. <button className="tlink" onClick={() => { setTab("all"); setSel(failed.id); }}>See why</button></>}</>}
      actions={<span className="stamp">Jobs keep running when the window is closed</span>}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
        <div className="tabs" role="tablist" aria-label="Filter jobs" style={{ flex: 1 }}>
          {(["all", "running", "done", "failed"] as Tab[]).map((t) => (
            <button key={t} className="tab" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>
              {{ all: "All", running: "Running", done: "Finished", failed: "Failed or stopped" }[t]}<span className="num">{counts[t]}</span>
            </button>
          ))}
        </div>
        <input className="field text" style={{ width: 280, height: 34 }} placeholder="Search jobs" aria-label="Search jobs" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <section className="card" aria-label="Jobs" style={{ padding: "12px 24px" }}>
        <div className="job-row small muted" style={{ height: 32 }}><span>Job</span><span>Kind</span><span>State</span><span>Progress or result</span><span style={{ textAlign: "right" }}>Took</span><span style={{ textAlign: "right" }}>Started</span><span /></div>
        {jobs == null ? <p className="muted" style={{ padding: "12px 0" }}>Loading…</p>
          : shown.length === 0 ? <div className="empty" style={{ margin: "8px 0" }}>{list.length ? "No jobs match." : "No jobs yet. Start an extract or an install and it shows up here."}</div>
          : shown.map((j, i) => <JobRow key={j.id} i={i} j={j} selected={j.id === selected?.id} onSelect={() => setSel(j.id)} onOpen={() => nav(jobRoute(j))} />)}
      </section>
      {selected && (
        <section className="card" aria-labelledby="lg">
          <div className="ch"><h2 id="lg">{setName(selected.argv?.[2] ?? selected.command)} · <span className="mono" style={{ fontSize: 14 }}>{shortId(selected.id)}</span></h2>
            <span className="tabs" style={{ border: 0, gap: 16 }}>
              <button className="tab" aria-pressed={!problemsOnly} onClick={() => setProblemsOnly(false)}>All lines</button>
              <button className="tab" aria-pressed={problemsOnly} onClick={() => setProblemsOnly(true)}>Warnings and errors</button>
            </span></div>
          <ErrorNote error={logs.error} />
          <div style={{ maxHeight: 280, overflowY: "auto" }} tabIndex={0} aria-label="Log lines"><LogLines events={logs.data} withTime /></div>
        </section>
      )}
    </Page>
  );
}

function JobRow({ j, i, selected, onSelect, onOpen }: { j: JobSnap; i: number; selected: boolean; onSelect: () => void; onOpen: () => void }) {
  const argv = j.argv ?? j.command.split(" ");
  const kind = KIND[`${argv[0]} ${argv[1]}`] ?? argv.slice(0, 2).join(" ");
  const state = { running: ["neu", "Running"], done: ["pos", "Finished"], failed: j.job_exit_code === 130 ? ["neu", "Stopped"] : ["neg", "Failed"], died: ["neg", "Ended unexpectedly"] }[j.state];
  const r: Ev = j.result ?? { type: "result" };
  const outcome = j.state === "done"
    ? (r.iso_deleted_bytes ? `Installed. ISO deleted, ${gb(r.iso_deleted_bytes)} GB back` : r.dest ? `Extracted to ${r.dest}` : "Finished")
    : (r.error ?? j.stderr?.trim().split("\n").pop() ?? "");
  return (
    <div className="job-row" onClick={onSelect} aria-selected={selected}
      style={{ height: 52, margin: "0 -12px", padding: "0 12px", borderRadius: 4, cursor: "pointer", background: selected ? "var(--raised)" : undefined, animation: "row-in .34s var(--ease-out) both", animationDelay: `${140 + i * 32}ms` }}>
      <div style={{ minWidth: 0 }}><div className="ellipsis" style={{ fontWeight: 600 }}>{setName(argv[2] ?? "") || kind}</div><div className="mono muted small">{shortId(j.id)}</div></div>
      <span className="soft">{kind}</span>
      <span><span className={`pill ${state[0]}`}>{state[1]}</span></span>
      {j.state === "running"
        ? <span style={{ display: "flex", alignItems: "center", gap: 12 }}><span className="track" style={{ flex: 1 }}><span className="fill" style={{ display: "block", transform: `scaleX(${(j.progress?.overall ?? 0) / 100})` }} /></span><span className="num">{Math.floor(j.progress?.overall ?? 0)}%</span></span>
        : <span className="soft ellipsis" title={outcome}>{outcome}</span>}
      <span className="num" style={{ textAlign: "right" }}>{dur(j.elapsed_s)}</span>
      <span className="num muted" style={{ textAlign: "right" }}>{jobStarted(j.id)}</span>
      <span style={{ textAlign: "right" }}>{j.state === "running" && <button className="tlink" onClick={(e) => { e.stopPropagation(); onOpen(); }}>Open</button>}</span>
    </div>
  );
}

export function LogLines({ events, withTime }: { events: Ev[] | null; withTime?: boolean }) {
  if (events == null) return <p className="muted">Loading…</p>;
  if (events.length === 0) return <p className="muted">Nothing logged yet.</p>;
  return (
    <div className="log" aria-live="off">
      {events.map((e, i) => (
        <div key={i} className={e.type === "warning" || e.type === "error" ? e.type : ""}>
          {e.ts && <span className="t">{new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", ...(withTime ? { second: "2-digit" } : {}) })}</span>}
          {e.type === "result" ? (e.ok ? "Finished." : `Stopped: ${e.error ?? `exit code ${e.exit_code}`}`) : shortPaths(e.msg)}
        </div>
      ))}
    </div>
  );
}

/** Engine lines carry full paths; the file name is what people read. */
const shortPaths = (m?: string) => (m ?? "").replace(/[A-Za-z]:\\(?:[^\\\s]+\\)+/g, "");
