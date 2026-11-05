// Browser-only stand-in for the engine (npm run dev without Tauri). Same event shapes as cli.py,
// sample data from the wireframe. Never used inside the Tauri app.
import type { EngineOutput, Ev } from "./engine";

const G = 1024 ** 3;
const T0 = Date.now();
const now = () => Date.now() / 1000;
const ok = (fields: Record<string, any>, events: Ev[] = [], code = 0): EngineOutput =>
  ({ code, events, result: { type: "result", exit_code: code, schema: 2, ok: code === 0 || code === 7, ...fields }, stderr: "" });
const fail = (code: number, error: string, fix?: string, events: Ev[] = []): EngineOutput =>
  ({ code, events: [...events, { type: "error", msg: error, fix }], result: { type: "result", exit_code: code, ok: false, error, fix }, stderr: "" });
const delay = <T,>(v: T, ms = 220) => new Promise<T>((r) => setTimeout(() => r(v), ms));

const DL = "D:\\Downloads";
const SETS = [
  { first: `${DL}\\Ashen.Tide.v1.4.2.part01.rar`, parts: 24, size: 47.3 * G, missing: [] as number[] },
  { first: `${DL}\\Hollow.Meridian-REPACK.part01.rar`, parts: 16, size: 31.84 * G, missing: [] },
  { first: `${DL}\\Pale.Harbor.Complete.part1.rar`, parts: 8, size: 14.66 * G, missing: [] },
  { first: `${DL}\\Kestrel.Run.v2.0.part01.rar`, parts: 11, size: 21.4 * G, missing: [] },
  { first: `${DL}\\Low.Orbit.part1.rar`, parts: 5, size: 9.8 * G, missing: [4] },
  { first: `${DL}\\Cinder.Pass.part1.rar`, parts: 3, size: 5.42 * G, missing: [] },
];
const ISOS = [{ path: `E:\\Downloads\\Vigil.of.Ostra.iso`, size: 71.62 * G, was_freed: false }];
const LOCKED = "Cinder.Pass";
const PASSWORD = "harbor";

interface MockJob { id: string; argv: string[]; start: number; seconds: number; end?: { code: number; fields: any }; stopped?: boolean; pw?: boolean }
const stamp = (minsAgo: number, tag: string) => {
  const d = new Date(T0 - minsAgo * 60000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}-${tag}`;
};
const jobs: MockJob[] = [
  { id: stamp(4.2, "3f9a"), argv: ["rar", "extract", SETS[0].first, "--dest", "D:\\Games\\Ashen Tide", "--delete", "--yes"], start: now() - 252, seconds: 600 },
  { id: stamp(15.2, "c9f3"), argv: ["iso", "install", ISOS[0].path, "--install-dir", "E:\\Games\\Vigil of Ostra", "--install-size-mb", "52000", "--buffer-gb", "5", "--silent", "--yes"], start: now() - 912, seconds: 2400 },
  { id: stamp(26, "e5d0"), argv: ["rar", "extract", SETS[3].first, "--delete", "--yes"], start: now() - 1560, seconds: 41,
    end: { code: 1, fields: { error: "Verification FAILED: checksum error in Kestrel.Run.v2.0.part07.rar - the archive is corrupt. Nothing was deleted.", parts_left: 11, parts: 11 } } },
  { id: stamp(80, "7c01"), argv: ["iso", "install", "E:\\Downloads\\Saltmarsh.iso", "--install-dir", "E:\\Games\\Saltmarsh", "--install-size-mb", "48000", "--silent", "--delete-iso", "--yes"], start: now() - 4800, seconds: 2290,
    end: { code: 0, fields: { setup_exit_code: 0, problems: [], unread: [], iso_deleted_bytes: 61.2 * G } } },
  { id: stamp(106, "9b44"), argv: ["iso", "install", ISOS[0].path, "--no-free", "--no-setup"], start: now() - 6360, seconds: 720,
    end: { code: 130, fields: { error: "Stopped with Ctrl+C." } } },
];

function snap(j: MockJob) {
  const t = now() - j.start;
  const frac = Math.min(1, t / j.seconds);
  if (!j.end && frac >= 1) j.end = { code: 0, fields: j.argv[0] === "rar" ? { dest: "D:\\Games\\Ashen Tide", files: 1204 } : { setup_exit_code: 0, problems: [] } };
  const state = j.end ? (j.end.code === 0 ? "done" : "failed") : "running";
  const s: any = { id: j.id, state, command: j.argv.join(" "), argv: j.argv, elapsed_s: Math.round(j.end ? j.seconds : t) };
  if (state === "running") {
    if (j.argv[0] === "rar") {
      const verify = j.argv[1] === "verify";
      s.progress = { phase: verify ? "verifying" : "extracting", overall: +(frac * 100).toFixed(1), part: Math.min(24, Math.floor(frac * 24) + 1), parts: 24,
        part_percent: Math.round((frac * 24 % 1) * 100), files_done: Math.round(1204 * frac), files: 1204, elapsed_s: Math.round(t), eta_s: Math.round(j.seconds - t) };
    } else {
      const sizes = [24 * G, 24 * G, 23.59 * G], total = sizes.reduce((a, b) => a + b);
      const read = total * frac, buffer = 5 * G;
      let left = Math.max(0, read - buffer), cum = 0;
      const bins = sizes.map((size, i) => {
        const r = Math.max(0, Math.min(size, read - cum)); cum += size;
        const f = Math.min(r, left); left -= f;
        return { path: `/setup-${i + 1}.bin`, size, read: r, freed: f };
      });
      s.progress = { overall: +(frac * 100).toFixed(1), bytes_read: read, freed: Math.max(0, read - buffer), installed: read * 52000 / 1024 / (total / G),
        paused: false, violations: 0, max_back: 120 * 1024 ** 2, bins };
    }
  }
  if (j.end) { s.job_exit_code = j.end.code; s.result = { exit_code: j.end.code, ok: j.end.code === 0, ...j.end.fields }; }
  return s;
}

const find = (id?: string) => (id ? jobs.find((j) => j.id === id || j.id.endsWith(id)) : jobs[0]);

function archive(first: string) {
  const set = SETS.find((s) => s.first === first) ?? SETS[0];
  const unpacked = set.size * 1.1015;
  return { first: set.first, volumes: Array.from({ length: set.parts }, (_, i) => set.first.replace(/part0*1\.rar$/i, `part${String(i + 1).padStart(2, "0")}.rar`)), files: 1204, packed: set.size, unpacked };
}

export async function mock(args: string[], stdin?: string): Promise<EngineOutput> {
  const [a, b] = args;
  const has = (f: string) => args.includes(f);
  const val = (f: string) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };

  if (a === "system" && b === "check")
    return delay(ok({ unrar: true, winfsp: true, fusepy: true, admin: true, missing: [] }, [
      { type: "check", name: "unrar", ok: true, source: "WinRAR", msg: "unrar OK" }]));
  if (a === "system" && b === "install-fusepy")
    return delay(ok({ already_installed: true }, [{ type: "event", msg: "fusepy is already installed." }]));
  if (a === "scan")
    return delay(ok({ folder: args[1], rar_sets: SETS.length, isos: ISOS.length }, [
      ...SETS.map((s) => ({ type: "rar_set", ...s })), ...ISOS.map((i) => ({ type: "found_iso", ...i }))]), 400);
  if (a === "jobs" && b === "list") return delay(ok({ jobs: jobs.length }, jobs.map((j) => ({ type: "job", ...snap(j) }))), 120);
  if (a === "jobs" && b === "status") {
    const j = find(args[2]); if (!j) return fail(2, "No job matches.");
    const s = snap(j); return delay(ok(s, [], s.state === "running" ? 7 : s.job_exit_code ?? 0), 80);
  }
  if (a === "jobs" && b === "logs") {
    const j = find(args[2]); if (!j) return fail(2, "No job matches.");
    const s = snap(j);
    const evs: Ev[] = j.argv[0] === "rar"
      ? [{ type: "event", msg: "Verifying all parts (reads everything, writes nothing)..." },
         ...(j.end?.code === 1 ? [{ type: "log", msg: "Checksum error in Kestrel.Run.v2.0.part07.rar" }, { type: "error", msg: j.end.fields.error }]
           : Array.from({ length: Math.max(0, (s.progress?.part ?? 25) - 1) }, (_, k) => ({ type: "log", msg: `Deleted ${j.argv[2].replace(/part0*1\.rar$/i, `part${String(k + 1).padStart(2, "0")}.rar`)}` })))]
      : [{ type: "event", msg: "Mounting as Z: (free mode, 5 GB buffer)..." }, { type: "event", msg: "Started setup.exe (silent)" },
         { type: "event", msg: "Started freeing /setup-1.bin" }, ...(s.state === "failed" ? [{ type: "error", msg: s.result.error }] : [])];
    const types = has("--type") ? args.slice(args.indexOf("--type") + 1) : null;
    const tail = Number(val("--tail") ?? 20);
    const list = evs.map((e, i) => ({ ...e, ts: j.start + i * 25 })).filter((e) => !types || types.includes(e.type)).slice(-tail);
    return delay(ok({ id: j.id }, list.map((e) => ({ type: "job_event", msg: e.msg, event: e }))), 100);
  }
  if (a === "jobs" && b === "stop") {
    const j = find(args[2]); if (j && !j.end) j.end = { code: 130, fields: { error: "Stopped with Ctrl+C." } };
    return delay(ok({ state: "failed" }), 600);
  }
  if (a === "rar") {
    const first = args[2];
    if (first.includes(LOCKED) && stdin?.trim() !== PASSWORD)
      return delay(fail(3, stdin ? "Wrong password." : "The archive is encrypted: a password is needed.", "echo <password> | ... --password-stdin"));
    const set = SETS.find((s) => s.first === first);
    if (set?.missing.length) return delay(fail(1, `Missing part ${set.missing.join(", ")} of this set. Download it, then try again.`));
    const info = archive(first);
    const dest = val("--dest") ?? first.replace(/\.part\d+\.rar$/i, "");
    const largest = info.packed / info.volumes.length;
    const needed = (has("--delete") ? info.unpacked - info.packed + largest : info.unpacked) + 1 * G;
    const space = { type: "space", dest, needed, free: 82.7 * G, enough: needed <= 82.7 * G };
    if (b === "inspect") return delay(ok({ parts: info.volumes.length, unpacked: info.unpacked, dest }, [{ type: "archive", ...info }, space]), 500);
    if (has("--background")) {
      const id = stamp(0, Math.random().toString(16).slice(2, 6));
      jobs.unshift({ id, argv: args.filter((x) => x !== "--background"), start: now(), seconds: b === "verify" ? 60 : 180 });
      return delay(ok({ job: id, state: "running" }, [{ type: "event", msg: `Started background job ${id}.`, job: id }]));
    }
    if (b === "extract" && has("--dry-run"))
      return delay(ok({ dry_run: true, dest, needs_yes: has("--delete") }, [space, { type: "archive", ...info },
        { type: "plan", steps: [...(has("--no-verify") ? [] : ["verify every part"]), `extract to ${dest}`, ...(has("--delete") ? [`delete the ${info.volumes.length} parts as they are used`] : [])] }]));
  }
  if (a === "iso") {
    const path = args[2];
    const size = Number(val("--install-size-mb") ?? 0) * 1024 ** 2;
    const buffer = Number(val("--buffer-gb") ?? 5);
    const free = 41.3 * G;
    const space = size ? { type: "space", free, needed: (buffer + 2) * G, growth: 0, enough: free >= (buffer + 2) * G } : null;
    const iso = { type: "iso", path, files: 38, size: 71.62 * G, has_setup: true, freeable: ["/setup-1.bin", "/setup-2.bin", "/setup-3.bin"] };
    const files = [["/setup-1.bin", 24], ["/setup-2.bin", 24], ["/setup-3.bin", 23.59], ["/setup.exe", 0.003]].map(([p, s]) => ({ type: "file", path: p, size: (s as number) * G }));
    if (b === "inspect") return delay(ok({ files: 38, size: iso.size, has_setup: true, was_freed: false, windows_mounted: false }, [iso, ...(has("--files") ? files : []), ...(space ? [space] : [])]), 300);
    if (b === "install" && has("--dry-run")) return delay(ok({ dry_run: true, mode: has("--no-free") ? "dry" : "free", needs_yes: !has("--no-free") },
      [{ type: "plan", steps: ["mount the ISO as a virtual drive and free it behind setup", "run setup.exe silently", "check setup's exit code and log, then unmount"] }]));
    if (b === "install" && has("--background")) {
      const id = stamp(0, Math.random().toString(16).slice(2, 6));
      jobs.unshift({ id, argv: args.filter((x) => x !== "--background"), start: now(), seconds: 300 });
      return delay(ok({ job: id, state: "running" }));
    }
  }
  return delay(fail(2, `Mock engine has no answer for: ${args.join(" ")}`));
}

export async function mockDisk(path: string) {
  const d = path.slice(0, 2).toUpperCase();
  const j = jobs[0];
  const frac = Math.min(1, (now() - j.start) / j.seconds);
  if (d === "E:") return { free: 43.74 * G, total: 476.94 * G };
  // D: dips while a part unpacks and recovers when it is deleted.
  const part = frac * 24, done = Math.floor(part);
  return { free: (82.7 - 52.1 * frac + 2 * done) * G, total: 953.87 * G };
}
