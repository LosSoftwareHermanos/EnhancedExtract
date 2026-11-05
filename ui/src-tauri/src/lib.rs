//! EnhancedExtract desktop shell.
//!
//! The UI never touches archives or drives itself: every action runs the engine's JSON CLI
//! (`<engine> --cli --json <command...>`) and returns its events plus the final `result` line.
//! Long work (extract, ISO install) is started with `--background`, so the engine runs it as a
//! detached job and the UI polls `jobs status <id>`; jobs survive the window closing.

use serde::Serialize;
use serde_json::Value;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

#[derive(Serialize)]
pub struct EngineOutput {
    /// The engine's exit code (see `cli.py schema`: 0 ok, 3 password, 4 space, 5 missing, 6 needs --yes, 7 still running).
    code: i32,
    /// Every JSON line before the result (archive, space, plan, progress, warning, error, ...).
    events: Vec<Value>,
    /// The final `{"type":"result", ...}` line, if the engine got that far.
    result: Option<Value>,
    /// The last part of stderr, for engine crashes that never printed a result.
    stderr: String,
}

/// Finds the engine, in this order:
/// 1. `EE_ENGINE`: path to an engine exe (run as `<exe> --cli ...`).
/// 2. `ee-engine.exe` next to this app: the release layout. It must be a PyInstaller build of
///    app.py WITHOUT `uac_admin`, or Windows refuses to start it from a normal process.
/// 3. Development: `python ../../app.py` from this crate (override Python with `EE_PYTHON`).
fn engine_command() -> Result<Command, String> {
    if let Ok(exe) = std::env::var("EE_ENGINE") {
        let mut c = Command::new(exe);
        c.arg("--cli");
        return Ok(c);
    }
    if let Some(dir) = std::env::current_exe().ok().and_then(|p| p.parent().map(PathBuf::from)) {
        let exe = dir.join("ee-engine.exe");
        if exe.is_file() {
            let mut c = Command::new(exe);
            c.arg("--cli");
            return Ok(c);
        }
    }
    let app = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("app.py");
    if app.is_file() {
        let python = std::env::var("EE_PYTHON").unwrap_or_else(|_| "python".into());
        let mut c = Command::new(python);
        c.arg(app).arg("--cli");
        return Ok(c);
    }
    Err("The EnhancedExtract engine was not found. Put ee-engine.exe next to this app, or set EE_ENGINE.".into())
}

fn run_engine(args: Vec<String>, stdin: Option<String>) -> Result<EngineOutput, String> {
    let mut cmd = engine_command()?;
    cmd.arg("--json")
        .args(&args)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(if stdin.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    let mut child = cmd.spawn().map_err(|e| format!("Could not start the engine: {e}"))?;
    if let (Some(text), Some(mut pipe)) = (stdin, child.stdin.take()) {
        // A password for --password-stdin; never put it on the command line.
        let _ = writeln!(pipe, "{text}");
    }
    let out = child.wait_with_output().map_err(|e| format!("The engine did not finish: {e}"))?;
    let mut events = Vec::new();
    let mut result = None;
    for line in String::from_utf8_lossy(&out.stdout).lines() {
        if let Ok(v) = serde_json::from_str::<Value>(line) {
            if v.get("type").and_then(Value::as_str) == Some("result") {
                result = Some(v);
            } else {
                events.push(v);
            }
        }
    }
    let err = String::from_utf8_lossy(&out.stderr);
    let stderr = err.chars().rev().take(2000).collect::<Vec<_>>().into_iter().rev().collect();
    Ok(EngineOutput { code: out.status.code().unwrap_or(-1), events, result, stderr })
}

/// Runs one engine command. Blocking work goes to a worker thread so the window stays responsive.
#[tauri::command]
async fn engine(args: Vec<String>, stdin: Option<String>) -> Result<EngineOutput, String> {
    tauri::async_runtime::spawn_blocking(move || run_engine(args, stdin))
        .await
        .map_err(|e| e.to_string())?
}

#[derive(Serialize)]
pub struct DiskSpace {
    free: u64,
    total: u64,
}

/// Free and total bytes of the drive that holds `path`.
#[tauri::command]
fn disk_space(path: String) -> Result<DiskSpace, String> {
    #[cfg(windows)]
    {
        use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;
        let wide: Vec<u16> = path.encode_utf16().chain(std::iter::once(0)).collect();
        let (mut free, mut total, mut total_free) = (0u64, 0u64, 0u64);
        let ok = unsafe { GetDiskFreeSpaceExW(wide.as_ptr(), &mut free, &mut total, &mut total_free) };
        if ok == 0 {
            return Err(format!("Could not read free space for {path}"));
        }
        Ok(DiskSpace { free, total })
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Err("Only supported on Windows".into())
    }
}

/// Starts this app again elevated (UAC prompt) and closes this copy. ISO installs need it:
/// game setups elevate themselves and can't see a drive mounted by a normal process.
/// The app does not start elevated by default because Windows blocks drag and drop from
/// Explorer into elevated windows.
#[tauri::command]
fn relaunch_as_admin(app: tauri::AppHandle) -> Result<(), String> {
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::Shell::ShellExecuteW;
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let w = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
        let (verb, file) = (w("runas"), w(&exe.to_string_lossy()));
        const SW_SHOWNORMAL: i32 = 1;
        let h = unsafe {
            ShellExecuteW(std::ptr::null_mut(), verb.as_ptr(), file.as_ptr(), std::ptr::null(), std::ptr::null(), SW_SHOWNORMAL)
        };
        if (h as isize) <= 32 {
            return Err("Windows did not start the app as administrator (the prompt was cancelled?).".into());
        }
        app.exit(0);
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = app;
        Err("Only supported on Windows".into())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![engine, disk_space, relaunch_as_admin])
        .run(tauri::generate_context!())
        .expect("error while running EnhancedExtract");
}
