use serde::Serialize;
use std::path::{Path, PathBuf};

#[derive(Clone, Serialize)]
pub struct ShellRequest {
    pub archive: String,
    pub delete: bool,
}

// Everything but RAR is opened by the engine through 7-Zip (sevenzip.py keeps the same list).
const OTHER_EXTS: &[&str] = &[
    "zip", "zipx", "7z", "tar", "gz", "tgz", "bz2", "tbz", "tbz2", "xz", "txz", "zst", "tzst", "lzma", "z", "cab",
    "wim", "arj", "lzh", "lha", "cpio",
];
const TAR_COMPRESSORS: &[&str] = &["gz", "bz2", "xz", "zst", "lzma", "z"];

fn digits_after_dot(name: &str, min: usize) -> Option<(usize, usize)> {
    // (index of the dot, digit count) when `name` ends in ".<digits>" with at least `min` digits
    let dot = name.rfind('.')?;
    let digits = &name[dot + 1..];
    (digits.len() >= min && digits.bytes().all(|b| b.is_ascii_digit())).then_some((dot, digits.len()))
}

/// `x.7z.001` -> Some(dot index of ".001"): a numbered volume of a known format.
fn volume_dot(lower: &str) -> Option<usize> {
    let (dot, _) = digits_after_dot(lower, 3)?;
    let ext = lower[..dot].rsplit('.').next()?;
    (lower[..dot].contains('.') && OTHER_EXTS.contains(&ext)).then_some(dot)
}

/// `x.z01` (the pieces of a classic split zip) -> Some(dot index).
fn zsplit_dot(lower: &str) -> Option<usize> {
    let dot = lower.rfind('.')?;
    let tail = &lower[dot + 1..];
    (tail.len() >= 3 && tail.starts_with('z') && tail[1..].bytes().all(|b| b.is_ascii_digit())).then_some(dot)
}

pub fn is_supported(path: &Path) -> bool {
    let lower = path.file_name().unwrap_or_default().to_string_lossy().to_ascii_lowercase();
    let ext = lower.rsplit('.').next().unwrap_or("");
    lower.contains('.') && (ext == "rar" || OTHER_EXTS.contains(&ext) || volume_dot(&lower).is_some() || zsplit_dot(&lower).is_some())
}

// canonicalize() adds a device-path prefix on Windows. UnRAR and Explorer expect
// ordinary drive or UNC paths at their command-line boundary.
pub fn ordinary_path(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    if let Some(unc) = text.strip_prefix(r"\\?\UNC\") { return PathBuf::from(format!(r"\\{unc}")); }
    if let Some(local) = text.strip_prefix(r"\\?\") { return PathBuf::from(local); }
    path
}

pub fn parse(args: &[String]) -> Result<Option<ShellRequest>, String> {
    if args.is_empty() { return Ok(None); }
    if !args[0].starts_with("--shell-") { return Ok(None); }
    if args.len() != 2 || !matches!(args[0].as_str(), "--shell-extract" | "--shell-extract-delete") {
        return Err("Expected --shell-extract <archive> or --shell-extract-delete <archive>.".into());
    }
    let path = Path::new(&args[1]);
    if !is_supported(path) {
        return Err("Select an archive (.rar, .zip, .7z, .tar.gz and other common formats).".into());
    }
    Ok(Some(ShellRequest { archive: first_volume(path).to_string_lossy().into_owned(), delete: args[0] == "--shell-extract-delete" }))
}

pub fn first_volume(path: &Path) -> PathBuf {
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    let lower = name.to_ascii_lowercase();
    // Only the first piece of a split set opens; the engine rejects later ones.
    if let Some(dot) = volume_dot(&lower) {
        let width = name.len() - dot - 1;
        return path.with_file_name(format!("{}.{:0>width$}", &name[..dot], "1", width = width));
    }
    if let Some(dot) = zsplit_dot(&lower) {
        return path.with_file_name(format!("{}.zip", &name[..dot]));
    }
    if lower.ends_with(".rar") {
        if let Some(i) = lower.rfind(".part") {
            let digits = &name[i + 5..name.len() - 4];
            if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
                let padded = path.with_file_name(format!("{}{:0>width$}{}", &name[..i + 5], "1", &name[name.len()-4..], width=digits.len()));
                let plain = path.with_file_name(format!("{}1{}", &name[..i+5], &name[name.len()-4..]));
                return if !padded.exists() && plain.is_file() { plain } else { padded };
            }
        }
    }
    path.to_path_buf()
}

/// The folder name an archive extracts into: `Game.part1.rar` -> `Game`, `Pack.tar.gz` -> `Pack`,
/// `Pack.7z.001` -> `Pack` (the same rule as default_dest in sevenzip.py).
pub fn archive_base(name: &str) -> String {
    let lower = name.to_ascii_lowercase();      // ASCII-only lowering keeps byte offsets valid in `name`
    let mut end = name.len();
    if let Some(dot) = volume_dot(&lower) {
        end = dot;                              // Pack.7z.001 -> Pack.7z, handled below
    } else if let Some(dot) = zsplit_dot(&lower) {
        return name[..dot].to_owned();          // Pack.z01 -> Pack
    }
    let (name, lower) = (&name[..end], &lower[..end]);
    for compressor in TAR_COMPRESSORS {
        if let Some(stem) = lower.strip_suffix(&format!(".tar.{compressor}")) {
            return name[..stem.len()].to_owned();   // Pack.tar.gz -> Pack
        }
    }
    let name = match lower.rfind('.') {
        Some(dot) if dot > 0 && (&lower[dot + 1..] == "rar" || OTHER_EXTS.contains(&&lower[dot + 1..])) => &name[..dot],
        _ => name,
    };
    match name.to_ascii_lowercase().rfind(".part") {
        Some(i) if name.len() > i + 5 && name[i + 5..].bytes().all(|b| b.is_ascii_digit()) => name[..i].to_owned(),
        _ => name.to_owned(),
    }
}

pub fn destination(archive: &Path, reserve: bool) -> Result<PathBuf, String> {
    let name = archive.file_name().ok_or("Invalid archive name")?.to_string_lossy();
    let base = archive_base(&name);
    let base = if base.is_empty() { "Extracted" } else { base.as_str() };
    let parent = archive.parent().ok_or("Archive has no parent folder")?;
    for n in 1..10000 {
        let candidate = parent.join(if n == 1 { base.to_owned() } else { format!("{base} ({n})") });
        if reserve {
            match std::fs::create_dir(&candidate) {
                Ok(()) => return Ok(candidate),
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(format!("Cannot create output folder: {e}")),
            }
        } else if !candidate.try_exists().map_err(|e| e.to_string())? {
            return Ok(candidate);
        }
    }
    Err("Too many output folders with this name.".into())
}

/// Windows share mode zero keeps double-clicks from opening competing launchers.
/// The file can remain on disk: only its open handle constitutes the lock.
pub fn session_lock(archive: &str) -> Result<std::fs::File, String> {
    use std::hash::{Hash, Hasher};
    let path = std::fs::canonicalize(archive).map_err(|e| e.to_string())?;
    let mut hash = std::collections::hash_map::DefaultHasher::new();
    path.to_string_lossy().to_lowercase().hash(&mut hash);
    let dir = std::env::var_os("LOCALAPPDATA").map(PathBuf::from).unwrap_or_else(std::env::temp_dir)
        .join("EnhancedExtract").join("shell-locks");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let mut options = std::fs::OpenOptions::new();
    options.read(true).write(true).create(true);
    #[cfg(windows)] {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    options.open(dir.join(format!("{:x}.lock", hash.finish())))
        .map_err(|e| format!("An extraction window may already be open for this archive. Check that window before trying again.\n\n{e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ordinary_launch_and_explicit_modes() {
        assert_eq!(ordinary_path(PathBuf::from(r"\\?\C:\Downloads\x")), PathBuf::from(r"C:\Downloads\x"));
        assert_eq!(ordinary_path(PathBuf::from(r"\\?\UNC\server\share\x")), PathBuf::from(r"\\server\share\x"));
        assert!(parse(&[]).unwrap().is_none());
        let request = parse(&["--shell-extract".into(), "C:\\some folder\\x.rar".into()]).unwrap().unwrap();
        assert!(!request.delete);
        assert!(parse(&["--shell-extract-delete".into(), "x.rar".into()]).unwrap().unwrap().delete);
        assert!(parse(&["--shell-extract".into()]).is_err());
        assert!(parse(&["--shell-extract".into(), "x.zip".into()]).unwrap().is_some());
        assert!(parse(&["--shell-extract".into(), "x.txt".into()]).is_err());
        assert!(parse(&["--shell-extract".into(), "x".into()]).is_err());
        assert!(parse(&["--shell-extract".into(), "x.rar".into(), "--yes".into()]).is_err());
    }

    #[test]
    fn later_parts_resolve_to_padded_first_volume() {
        assert_eq!(first_volume(Path::new("Game.part003.rar")), PathBuf::from("Game.part001.rar"));
        assert_eq!(first_volume(Path::new("Game.PART12.RAR")), PathBuf::from("Game.PART01.RAR"));
        assert_eq!(first_volume(Path::new("Game.rar")), PathBuf::from("Game.rar"));
        assert_eq!(first_volume(Path::new("Game.partners.rar")), PathBuf::from("Game.partners.rar"));
        assert_eq!(first_volume(Path::new("İstanbul.part003.rar")), PathBuf::from("İstanbul.part001.rar"));
    }

    #[test]
    fn split_sets_resolve_to_the_piece_the_engine_opens() {
        assert_eq!(first_volume(Path::new("Pack.7z.003")), PathBuf::from("Pack.7z.001"));
        assert_eq!(first_volume(Path::new("Pack.ZIP.0012")), PathBuf::from("Pack.ZIP.0001"));
        assert_eq!(first_volume(Path::new("Pack.z05")), PathBuf::from("Pack.zip"));
        assert_eq!(first_volume(Path::new("Pack.zip")), PathBuf::from("Pack.zip"));
        assert_eq!(first_volume(Path::new("Pack.tar.gz")), PathBuf::from("Pack.tar.gz"));
        // a numbered file that is not a known archive format is left alone
        assert_eq!(first_volume(Path::new("movie.mkv.003")), PathBuf::from("movie.mkv.003"));
        assert!(is_supported(Path::new("Pack.7z.002")) && is_supported(Path::new("a.z01")) && is_supported(Path::new("A.TAR.GZ")));
        assert!(!is_supported(Path::new("movie.mkv.003")) && !is_supported(Path::new("notes.txt")) && !is_supported(Path::new("zip")));
    }

    #[test]
    fn output_folder_is_named_after_the_archive() {
        for (name, want) in [("Game.part01.rar", "Game"), ("Pack.zip", "Pack"), ("Pack.tar.gz", "Pack"), ("My.Game.v2.7z", "My.Game.v2"),
                             ("Pack.7z.001", "Pack"), ("Pack.zip.001", "Pack"), ("Pack.z01", "Pack"), ("Pack.TGZ", "Pack"),
                             ("data.tar", "data"), ("İstanbul.7z", "İstanbul"), (".zip", ".zip")] {
            assert_eq!(archive_base(name), want, "{name}");
        }
    }

    #[test]
    fn reserved_destinations_never_reuse_existing_output() {
        let temp = std::env::temp_dir().join(format!("ee-shell-{}-{}", std::process::id(), std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
        std::fs::create_dir(&temp).unwrap();
        let archive = temp.join("Game.part01.rar");
        std::fs::write(&archive, "archive fixture").unwrap();
        let lock = session_lock(archive.to_str().unwrap()).unwrap();
        #[cfg(windows)] assert!(session_lock(archive.to_str().unwrap()).is_err());
        drop(lock);
        drop(session_lock(archive.to_str().unwrap()).unwrap());
        let plain = temp.join("Other.part1.rar");
        std::fs::write(&plain, "archive fixture").unwrap();
        assert_eq!(first_volume(&temp.join("Other.part12.rar")), plain);
        let preview = destination(&archive, false).unwrap();
        assert_eq!(preview, temp.join("Game"));
        assert!(!preview.exists());
        let reserved = destination(&archive, true).unwrap();
        std::fs::write(reserved.join("keep.txt"), "keep").unwrap();
        let next = destination(&archive, true).unwrap();
        assert_eq!(next, temp.join("Game (2)"));
        assert_eq!(std::fs::read_to_string(reserved.join("keep.txt")).unwrap(), "keep");
        std::fs::remove_dir_all(temp).unwrap();
    }
}
