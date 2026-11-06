# EnhancedExtract UI (Tauri)

A new desktop front end for EnhancedExtract, built alongside the original Tkinter app (`app.py`), which
is unchanged. The UI has no Python in it: it drives the existing engine through its JSON CLI.

## How it talks to the engine

Every action runs `<engine> --cli --json <command ...>` (see `python app.py --cli schema`) and reads
the JSON lines it prints; the last line is always `{"type": "result", "exit_code": ...}`.

| Screen | Engine commands |
| --- | --- |
| Library | `scan FOLDER`, `system check`, `jobs list` |
| Extract RAR | `rar inspect` (with and without `--delete`, for both space figures), `rar extract --dry-run`, then `rar extract --background [--yes]` |
| Install from ISO | `iso inspect --files`, `iso install --dry-run`, then `iso install --background --yes` |
| Running screens | `jobs status ID` every second, `jobs logs ID` every few seconds, `jobs stop ID` |
| Jobs | `jobs list`, `jobs logs` |

Long work always runs as an engine background job, so it keeps going if the window closes and the UI
only polls. Passwords go over stdin (`--password-stdin`), never on the command line.

The Rust side (`src-tauri/src/lib.rs`) exposes `engine` (run the CLI, return its events),
`disk_space` (free/total bytes of a drive) and `relaunch_as_admin` (UAC prompt, for ISO installs).
It finds the engine in this order:

1. `EE_ENGINE`: path to an engine exe.
2. `engine\ee-engine.exe` next to the app (where the installer puts it), or `ee-engine.exe` beside it.
   `build\build-engine.bat` builds it from `engine.py` (CLI and virtual drive, no Tk) as a folder, not
   one file (the UI calls it about once a second), and **without** `uac_admin`, or Windows refuses to
   start it from a normal process.
3. Development: `python ../../app.py` (set `EE_PYTHON` to use a venv's python).

## Run it

Needs Node 20+, the Rust toolchain (`rustup`, MSVC target) and the MSVC C++ build tools (WebView2 ships
with Windows 11).

```bash
cd ui
npm install
npm run tauri dev      # the app, with the real engine
npm run dev            # browser only, at http://localhost:1420, with a mock engine (no Rust needed)
..\build\build-engine.bat   # engine first: build\dist\ee-engine (bundled by the next step)
npm run tauri build    # installer in src-tauri/target/release/bundle/nsis
```

The installer installs for the current user (no admin prompt) with a Start menu shortcut, and puts the
engine in `engine\` beside `EnhancedExtract.exe`. Jobs and logs of the installed app live in
`%LOCALAPPDATA%\EnhancedExtract`.

In the browser preview, `#rar`, `#rarJob`, `#iso`, `#isoJob` and `#jobs` open a screen directly.

## Explorer quick extraction

The Windows installer adds entries to a single `.rar` file's classic context menu
(**Show more options** on Windows 11):

- **Extract with EnhancedExtract** verifies all parts and extracts into a new folder beside
  the archive. It keeps the source archives and starts without opening the dashboard.
- **Extract and free space with EnhancedExtract...** shows the engine's dry-run plan,
  required/free space and the parts to delete. Safe mode starts with **Extract & delete**;
  it holds each file's parts until the file is extracted and flushed. If only early deletion
  fits, a separate warning checkbox is required because interruption can lose a file.

Selecting a later `.partN.rar` resolves to the first volume, including zero-padded names.
If `Game` already exists, output goes to `Game (2)`, then `Game (3)`, etc. Folder reservation
uses atomic directory creation so existing output is never selected for overwriting.
The compact window handles passwords, progress, stop confirmation, errors, and opening the
completed output folder. Closing it leaves the engine job running; the main app's Jobs screen
can follow it. Reopening a running extraction attaches to the existing job. A Windows file
handle lock prevents competing quick-extract windows for the same archive while one is open.
Passwords remain in memory and travel over stdin, then the existing background-job environment.

The installer registers a per-user collapsible **EnhancedExtract** submenu (with a third item,
**Open with EnhancedExtract**) under `SystemFileAssociations\.rar\shell`, without changing default
file associations. It avoids `AppliesTo` filters, which do not show on stripped-down Windows builds.
Uninstallation removes only that key. The installer also marks the Desktop and Start Menu shortcuts
"Run as administrator" (needed for ISO install); right-click extraction stays unelevated.
Registration is in `src-tauri/windows/hooks.nsh`. The UI executable accepts
`--shell-extract "C:\Downloads\Game.rar"` and
`--shell-extract-delete "C:\Downloads\Game.rar"`; the latter still requires confirmation.
ZIP support is not included: the engine currently extracts RAR archives.

Both the dashboard and compact window support resuming a stopped delete run. Keep the
`<set>.ee-resume.json` journal beside the remaining parts and reopen the set. The original
destination is retained, completed files are skipped, and early-mode losses are listed.
Safe mode retains every part of a solid set until extraction finishes. The dashboard compares
safe, early, and keep estimates; it selects early deletion when safe does not fit, with a
separate confirmation before starting. Job snapshots retain their last recorded progress
after a stop or failure, including when the dashboard is reopened.

Check with `npm run build`, `cargo test --lib` from `src-tauri`, and
`python -m unittest discover -s tests` from the repository root. For a packaged smoke test,
install the built NSIS installer, right-click a disposable multipart RAR, and check later-part
selection, existing destination preservation, password retry, deletion-plan cancellation,
and completion. Use disposable fixtures for destructive-mode tests.

## UX rules this follows

- Every action shows its own busy state on its button; nothing blocks the window.
- Errors appear inside the block that failed, with the engine's `fix` when it has one, and a retry.
- Deletion choices name what goes. Safe RAR deletion starts from the selected action;
  early RAR deletion, ISO freeing, and ISO deletion require separate confirmation.
- Every disabled button says why (tooltip and, on ISO set-up, a status line).
- Real engine numbers only: both space figures come from `rar inspect`, ISO space from `iso inspect`.
- Dialogs trap focus, close on Esc, and return focus. Progress bars use `role="progressbar"`; job
  results are announced through a polite live region. Reduced motion is respected.
- Shortcuts: Ctrl+O opens a .rar or .iso, F5 rescans the Library. Drag a file onto the window to set it up.
- The executable starts unelevated by default, supporting Explorer drag and drop. Installed
  shortcuts request administrator rights for ISO installs; an unelevated dashboard also offers
  "Restart as admin" when needed.
- Choices are remembered (folder, verify/delete, buffer, silent setup).
- Fonts are bundled; the app makes no network requests.

## Look

The brand comes from the logo: black Σ on yellow with two cut corners.

- One yellow field per screen, black type on it (the Library summary, the space decision on set-up,
  the progress on running screens); the primary action is a yellow cut-corner button.
- Type: Oxanium (squared and chamfered like the Σ, equal-width digits) for titles and every number;
  Bai Jamjuree for running text. Both OFL, bundled through Fontsource.
- The real logo (`src/assets/logo.png`, from `icon.png`) sits at the top of the rail and the real
  wordmark (`src/assets/wordmark.png`, cropped from `EE/title/title2.png`) in the title bar.
- Parts are drawn as a strip, one segment per archive part: missing parts are outlined in red,
  used parts fill in, deleted parts are struck through.
