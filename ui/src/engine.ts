// The bridge to the Python engine. In the Tauri app every call runs `<engine> --cli --json <args>`;
// in a plain browser (npm run dev) a mock answers instead, so the UI can be built and checked without Rust.
import { mock, mockDisk } from "./mock";

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

export async function pickFolder(defaultPath?: string): Promise<string | null> {
  if (!inTauri) return window.prompt("Folder", defaultPath ?? "") || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ directory: true, defaultPath });
  return typeof r === "string" ? r : null;
}

export async function pickArchive(): Promise<string | null> {
  if (!inTauri) return window.prompt("First .rar part or .iso file", "") || null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ filters: [{ name: "RAR sets and ISOs", extensions: ["rar", "iso"] }] });
  return typeof r === "string" ? r : null;
}

// ---------- shapes of the events the screens read ----------
export interface RarSet { first: string; parts: number; size: number; missing: number[] }
export interface FoundIso { path: string; size: number; was_freed: boolean }
export interface Archive { first: string; volumes: string[]; files: number; packed: number; unpacked: number }
export interface Space { dest?: string; needed: number; free: number; enough: boolean; growth?: number }
export interface IsoInfo { path: string; files: number; size: number; has_setup: boolean; freeable: string[] }
export interface Bin { path: string; size: number; read: number; freed: number }
export interface Progress {
  phase?: string; overall: number; part?: number; parts?: number; files_done?: number; files?: number;
  eta_s?: number | null; elapsed_s?: number;
  bytes_read?: number; freed?: number; installed?: number; paused?: boolean; violations?: number; max_back?: number; bins?: Bin[];
}
export interface JobSnap {
  id: string; state: "running" | "done" | "failed" | "died"; command: string; argv?: string[]; elapsed_s: number;
  progress?: Progress; warnings?: string[]; job_exit_code?: number; result?: Ev; stderr?: string;
}
export interface SystemCheck { unrar: boolean; winfsp: boolean; fusepy: boolean; admin: boolean; hints: Record<string, string>; unrarSource?: string }

export async function systemCheck(): Promise<SystemCheck> {
  const out = await call(["system", "check"], { allow: [1] });
  const r: Ev = out.result ?? { type: "result" };
  const hints: Record<string, string> = {};
  for (const h of ofType(out, "hint")) hints[h.name] = h.msg ?? "";
  return { unrar: !!r.unrar, winfsp: !!r.winfsp, fusepy: !!r.fusepy, admin: !!r.admin, hints, unrarSource: first(out, "check")?.source };
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
