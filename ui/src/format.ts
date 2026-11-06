// Sizes use 1024-based units labelled GB, the way Explorer shows them, so numbers match what users see.
export const GiB = 1024 ** 3;
export const MiB = 1024 ** 2;

export const gb = (bytes: number) => (bytes / GiB).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function dur(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (h) return `${h} h ${String(m).padStart(2, "0")} m`;
  if (!m) return `${r} s`;
  return `${m} m ${String(r).padStart(2, "0")} s`;
}

export const int = (n: number) => Math.round(n).toLocaleString("en-US");

export const basename = (p: string) => p.split(/[\\/]/).pop() ?? p;
export const dirname = (p: string) => p.replace(/[\\/][^\\/]*$/, "");
export const drive = (p: string) => (/^[a-z]:/i.exec(p)?.[0].toUpperCase() ?? "") as string;

/** "Ashen.Tide.v1.4.2.part01.rar" -> "Ashen Tide v1.4.2" */
export function setName(path: string): string {
  const b = basename(path).replace(/\.part\d+\.rar$/i, "").replace(/\.(rar|iso)$/i, "");
  return b.replace(/[._](?=[A-Za-z])/g, " ").replace(/_/g, " ").trim();
}

/** Job ids look like 20261105-221500-ab12; the time is when it started. */
export function jobStarted(id: string): string {
  const m = /^\d{8}-(\d\d)(\d\d)/.exec(id);
  return m ? `${m[1]}:${m[2]}` : "—";
}
export const shortId = (id: string) => id.split("-").pop() ?? id;

/** Splits a command line the way the engine's list2cmdline built it (quotes around spaces). */
export function argv(cmd: string): string[] {
  const out: string[] = [];
  const re = /"((?:[^"\\]|\\.)*)"|(\S+)/g;
  for (let m; (m = re.exec(cmd)); ) out.push(m[1] ?? m[2]);
  return out;
}
export function flag(args: string[], name: string): string | undefined {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

export const clamp = (n: number, lo = 0, hi = 100) => Math.min(hi, Math.max(lo, n));
