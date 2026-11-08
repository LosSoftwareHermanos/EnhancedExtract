// The bridge to the Python engine. In the Tauri app every call runs `<engine> --cli --json <args>`;
// in a plain browser (npm run dev) a mock answers instead, so the UI can be built and checked without Rust.
import { ARCHIVE_EXTENSIONS } from "./format";
import { mock, mockDestination, mockDisk } from "./mock";

export type Ev = { type: string; msg?: string; [k: string]: any };
export interface EngineOutput { code: number; events: Ev[]; result: Ev | null; stderr: string }

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Exit codes from `cli.py schema`. */
export const EXIT = { OK: 0, FAILED: 1, BAD_INPUT: 2, PASSWORD: 3, SPACE: 4, MISSING: 5, NEEDS_YES: 6, RUNNING: 7 } as const;

export class EngineError extends Error {
  constructor(public code: number, message: string, public fix?: string, public out?: EngineOutput) {
    super(message);
  }
}

async function raw(args: string[], stdin?: string): Promise<EngineOutput> {
  if (!inTauri) return mock(args, stdin);
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<EngineOutput>("engine", { args, stdin: stdin ?? null });
}

/** Runs a command; throws EngineError unless the exit code is 0 or one of `allow`. */
export async function call(args: string[], opts: { stdin?: string; allow?: number[] } = {}): Promise<EngineOutput> {
  let out: EngineOutput;
  try {
    out = await raw(args, opts.stdin);
  } catch (e) {
    throw new EngineError(-1, String(e));
  }
  if (out.code === 0 || opts.allow?.includes(out.code)) return out;
  const r: Ev = out.result ?? { type: "result" };
  const lastError = [...out.events].reverse().find((e) => e.type === "error");
  const msg = r.error ?? lastError?.msg ?? (out.stderr.trim().split("\n").pop() || `The engine stopped with exit code ${out.code}.`);
  throw new EngineError(out.code, msg, r.fix ?? lastError?.fix, out);
}

export const ofType = (out: EngineOutput, type: string) => out.events.filter((e) => e.type === type);
export const first = (out: EngineOutput, type: string) => out.events.find((e) => e.type === type);

export async function diskSpace(path: string): Promise<{ free: number; total: number } | null> {
  if (!path) return null;
  if (!inTauri) return mockDisk(path);
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<{ free: number; total: number }>("disk_space", { path }).catch(() => null);
}

export async function relaunchAsAdmin(): Promise<void> {
  if (!inTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("relaunch_as_admin");
}

/** Explorer quick extract: the next free "<archive name> (n)" folder beside the archive; `reserve` creates it. */
export async function shellDestination(reserve: boolean): Promise<string> {
  if (!inTauri) return mockDestination();
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string>("shell_destination", { reserve });
}

export async function openFolder(path: string): Promise<void> {
  if (!inTauri) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("open_output", { path });
}

export async function closeWindow(): Promise<void> {
  if (!inTauri) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().close();
}

export async function pickFolder(defaultPath?: string): Promise<string | null> {
  if (!inTauri) return window.prompt("Folder", defaultPath ?? "") || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ directory: true, defaultPath });
  return typeof r === "string" ? r : null;
}

export async function pickArchive(): Promise<string | null> {
  if (!inTauri) return window.prompt("Archive (.rar, .zip, .7z, .tar.gz ...) or .iso file", "") || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ filters: [
    { name: "Archives and ISOs", extensions: [...ARCHIVE_EXTENSIONS, "iso"] },
    { name: "All files", extensions: ["*"] },
  ] });
  return typeof r === "string" ? r : null;
}

// ---------- shapes of the events the screens read ----------
/** `busy`: part numbers still being written by another program (an unfinished copy or download). */
export interface RarSet { first: string; parts: number; size: number; missing: number[]; busy?: number[]; more_after?: boolean }
/** A zip, 7z, tar, gz ... (anything but RAR): one file, or a split set (`parts` > 1). */
export interface OtherArchive { first: string; format: string; parts: number; size: number; missing: number[]; busy?: number[] }
export interface FoundIso { path: string; size: number; was_freed: boolean; busy?: boolean }
/** `files` is 0 when the engine could not count them cheaply (a very large .tar.gz). */
export interface Archive { first: string; volumes: string[]; files: number; packed: number; unpacked: number; format?: string }
/** With --delete: `mode` "safe" (a part goes once every file in it is out; a stop resumes) or "early"
 *  (each part goes as soon as it is read), and what each would need. Archives that are not RAR report
 *  `generic`: nothing can be freed while reading, so `mode` is "after" (the archive goes once extraction
 *  finished cleanly) or "keep". */
export interface Space {
  dest?: string; needed: number; free: number; enough: boolean; growth?: number;
  mode?: "safe" | "early" | "keep" | "after"; needed_safe?: number; needed_early?: number; early_fits?: boolean; solid?: boolean;
  generic?: boolean;
}
export interface IsoInfo { path: string; files: number; size: number; has_setup: boolean; freeable: string[] }
export interface IsoStatus { path: string; exists: boolean; windows_mounted: boolean }
export interface Bin { path: string; size: number; read: number; freed: number }
export interface Progress {
  /** 7-Zip jobs report one percentage for the whole archive, not per part. */
  whole?: boolean;
  phase?: string; overall: number; part?: number; parts?: number; files_done?: number; files?: number;
  eta_s?: number | null; elapsed_s?: number;
  bytes_read?: number; freed?: number; installed?: number; paused?: boolean; violations?: number; max_back?: number; bins?: Bin[];
}
export interface JobSnap {
  id: string; state: "running" | "done" | "failed" | "died"; command: string; argv?: string[]; elapsed_s: number;
  progress?: Progress; warnings?: string[]; job_exit_code?: number; result?: Ev; stderr?: string;
}
export interface SystemCheck { unrar: boolean; sevenzip: boolean; winfsp: boolean; fusepy: boolean; admin: boolean; hints: Record<string, string>; unrarSource?: string }

export async function isoStatus(path: string): Promise<IsoStatus> {
  const out = await call(["iso", "status", path]);
  return (out.result ?? {}) as unknown as IsoStatus;
}

export async function systemCheck(): Promise<SystemCheck> {
  const out = await call(["system", "check"], { allow: [1] });
  const r: Ev = out.result ?? { type: "result" };
  const hints: Record<string, string> = {};
  for (const h of ofType(out, "hint")) hints[h.name] = h.msg ?? "";
  return { unrar: !!r.unrar, sevenzip: !!r.sevenzip, winfsp: !!r.winfsp, fusepy: !!r.fusepy, admin: !!r.admin, hints,
    unrarSource: ofType(out, "check").find((c) => c.name === "unrar")?.source };
}

/** pip-installs fusepy into the engine's own Python (a no-op in the frozen exe, which bundles it). */
export async function installFusepy(): Promise<void> {
  await call(["system", "install-fusepy"]);
}

export async function jobStatus(id: string): Promise<JobSnap> {
  const out = await call(["jobs", "status", id], { allow: [1, 3, 4, 5, 6, 7, 130] });
  const r: Ev = out.result ?? { type: "result" };
  return r as unknown as JobSnap;
}

export async function jobsList(limit = 30): Promise<JobSnap[]> {
  const out = await call(["jobs", "list", "--limit", String(limit)]);
  return ofType(out, "job") as unknown as JobSnap[];
}

export async function jobLogs(id: string, tail = 40, types?: string[]): Promise<Ev[]> {
  const args = ["jobs", "logs", id, "--tail", String(tail)];
  if (types?.length) args.push("--type", ...types);
  const out = await call(args);
  return ofType(out, "job_event").map((e) => e.event as Ev);
}
