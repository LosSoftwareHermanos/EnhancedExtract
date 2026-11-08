// Sizes use 1024-based units labelled GB, the way Explorer shows them, so numbers match what users see.
export const GiB = 1024 ** 3;
export const MiB = 1024 ** 2;

export type Unit = "KB" | "MB" | "GB";
const UNIT_BYTES: Record<Unit, number> = { KB: 1024, MB: MiB, GB: GiB };
/** The unit a size reads best in: archives are often a few MB, game sets tens of GB. */
export const unitFor = (bytes: number): Unit => (bytes >= GiB * 0.995 ? "GB" : bytes >= MiB * 0.995 ? "MB" : "KB");
/** `bytes` in a fixed unit, so an animated number keeps one unit while it counts. */
export const scaled = (bytes: number, unit: Unit) => (bytes / UNIT_BYTES[unit]).toLocaleString("en-US", {
  minimumFractionDigits: unit === "GB" ? 2 : 1, maximumFractionDigits: unit === "GB" ? 2 : 1 });
/** "3.2 MB", "47.30 GB" */
export const size = (bytes: number) => { const u = unitFor(bytes); return `${scaled(bytes, u)} ${u}`; };

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

// Formats beyond RAR are opened with 7-Zip by the engine (sevenzip.py keeps the same list).
const OTHER = "zip|zipx|7z|tar|gz|tgz|bz2|tbz|tbz2|xz|txz|zst|tzst|lzma|z|cab|wim|arj|lzh|lha|cpio";
const OTHER_PATH = new RegExp(`\\.(${OTHER})$|\\.(${OTHER})\\.\\d{3,}$|\\.z\\d{2,}$`, "i");
/** Extensions for file pickers (no dots). */
export const ARCHIVE_EXTENSIONS = ["rar", "r00", "dat", ...OTHER.split("|"), "001"];

export const isIso = (p: string) => /\.iso$/i.test(p);
/** Game.part1.dat: a RAR set some sites rename; the engine checks the bytes before using it. */
export const isRar = (p: string) => /\.(rar|r\d\d)$/i.test(p) || /\.part\d+\.dat$/i.test(p);
/** Any archive the engine can extract: RAR sets, zip, 7z, tar and friends, split sets (.7z.001, .z01). */
export const isArchive = (p: string) => isRar(p) || OTHER_PATH.test(p);

/** "Pack.tar.gz" -> "TAR.GZ", "Pack.7z.001" -> "7Z", "Game.part1.rar" -> "RAR" */
export function archiveFormat(path: string): string {
  const b = basename(path);
  if (isRar(b)) return "RAR";
  if (/\.tar\.(gz|bz2|xz|zst|lzma|z)$/i.test(b)) return b.slice(b.toLowerCase().lastIndexOf(".tar") + 1).toUpperCase();
  const volume = /\.([a-z0-9]+)\.\d{3,}$/i.exec(b);
  if (volume) return volume[1].toUpperCase();
  if (/\.z\d{2,}$/i.test(b)) return "ZIP";
  return (/\.([a-z0-9]+)$/i.exec(b)?.[1] ?? "").toUpperCase();
}

/** "Ashen.Tide.v1.4.2.part01.rar" -> "Ashen Tide v1.4.2"; "Pack.tar.gz" -> "Pack" */
export function setName(path: string): string {
  const b = basename(path)
    .replace(/\.part\d+\.(rar|dat)$/i, "")
    .replace(/\.tar\.(gz|bz2|xz|zst|lzma|z)$/i, "")
    .replace(new RegExp(`\\.(${OTHER})\\.\\d{3,}$`, "i"), "")
    .replace(new RegExp(`\\.(rar|iso|${OTHER})$`, "i"), "")
    .replace(/\.z\d{2,}$/i, "");
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
