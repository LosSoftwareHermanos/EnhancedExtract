use serde::Serialize;
use std::path::{Path, PathBuf};

#[derive(Clone, Serialize)]
pub struct ShellRequest {
    pub archive: String,
    pub delete: bool,
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
        return Err("Expected --shell-extract <archive.rar> or --shell-extract-delete <archive.rar>.".into());
    }
    let path = Path::new(&args[1]);
    if !path.extension().is_some_and(|x| x.eq_ignore_ascii_case("rar")) {
        return Err("Select a RAR archive (.rar).".into());
    }
    Ok(Some(ShellRequest { archive: first_volume(path).to_string_lossy().into_owned(), delete: args[0] == "--shell-extract-delete" }))
}

pub fn first_volume(path: &Path) -> PathBuf {
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    let lower = name.to_ascii_lowercase();
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

pub fn destination(archive: &Path, reserve: bool) -> Result<PathBuf, String> {
    let stem = archive.file_stem().ok_or("Invalid archive name")?.to_string_lossy();
    let lower = stem.to_ascii_lowercase();
    let base = match lower.rfind(".part") {
        Some(i) if stem[i+5..].bytes().all(|b| b.is_ascii_digit()) && stem.len() > i+5 => &stem[..i],
        _ => &stem,
    };
    let base = if base.is_empty() { "Extracted" } else { base };
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
        assert!(parse(&["--shell-extract".into(), "x.zip".into()]).is_err());
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
