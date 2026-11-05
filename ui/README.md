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

The Rust side (`src-tauri/src/lib.rs`) has three commands: `engine` (run the CLI, return its events),
`disk_space` (free/total bytes of a drive) and `relaunch_as_admin` (UAC prompt, for ISO installs).
It finds the engine in this order:

1. `EE_ENGINE`: path to an engine exe.
2. `ee-engine.exe` next to the app (release layout). Build it with PyInstaller **without** `uac_admin`,
   or Windows refuses to start it from a normal process.
3. Development: `python ../../app.py` (set `EE_PYTHON` to use a venv's python).

## Run it

Needs Node 20+, the Rust toolchain (`rustup`, MSVC target) and the MSVC C++ build tools (WebView2 ships
with Windows 11).

```bash
cd ui
npm install
npm run tauri dev      # the app, with the real engine
npm run dev            # browser only, at http://localhost:1420, with a mock engine (no Rust needed)
npm run tauri build    # installer in src-tauri/target/release/bundle
```

In the browser preview, `#rar`, `#rarJob`, `#iso`, `#isoJob` and `#jobs` open a screen directly.

## UX rules this follows

- Every action shows its own busy state on its button; nothing blocks the window.
- Errors appear inside the block that failed, with the engine's `fix` when it has one, and a retry.
- Anything that deletes data (delete-as-you-go, freeing an ISO, deleting an ISO, force stop) asks first,
  names what goes, and needs an explicit tick. The safe button has focus.
- Every disabled button says why (tooltip and, on ISO set-up, a status line).
- Real engine numbers only: both space figures come from `rar inspect`, ISO space from `iso inspect`.
- Dialogs trap focus, close on Esc, and return focus. Progress bars use `role="progressbar"`; job
  results are announced through a polite live region. Reduced motion is respected.
- Shortcuts: Ctrl+O opens a .rar or .iso, F5 rescans the Library. Drag a file onto the window to set it up.
- The app does not start elevated, because Windows blocks drag and drop into elevated windows; ISO
  set-up offers "Restart as admin" when it's needed.
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
