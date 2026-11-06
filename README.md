<p align="center"><img src="docs/assets/banner.svg" alt="EnhancedExtract" width="100%"></p>

**Windows archive extraction for tight disk space.** Right-click extraction, an optional desktop dashboard, and a standalone CLI, powered by the same engine.

[Download beta](https://github.com/gustavofring1483369/EnhancedExtract/releases/tag/v0.1.0-beta.1) · [User guide](docs/USER_GUIDE.md) · [Report a bug](https://github.com/gustavofring1483369/EnhancedExtract/issues)

## Choose how to use it

| Way | Get started |
|---|---|
| **Right-click** | Install the Windows app, then right-click a `.rar` and choose **EnhancedExtract**. On Windows 11, use **Show more options**. |
| **Desktop GUI** | Use the same installer, then open EnhancedExtract for space estimates, extraction options, and job history. |
| **CLI** | Download the standalone CLI ZIP, unzip it, and run `ee-engine.exe`. No desktop installation or Python required. |

The installer adds Explorer integration without replacing your default archive app. Right-click extraction opens a compact window; the dashboard is optional. ZIP and 7z extraction are not supported yet.

## What it does

- Extracts multipart RAR sets, verifies checksums first, and checks available disk space.
- Frees archive space as files finish, with a journal for resuming stopped delete runs.
- Offers ordinary extraction that keeps every archive part.
- Handles passwords and background jobs through the GUI or CLI.
- Includes an experimental ISO installation workflow that can free source-image space while setup runs.

**Space savings depend on the archive.** Safe mode retains the parts needed by unfinished files. Solid archives and very large files may require room for the whole output before any parts can be deleted.

## Download and run

Get the files from the [beta release](https://github.com/gustavofring1483369/EnhancedExtract/releases/tag/v0.1.0-beta.1):

- **Desktop:** `EnhancedExtract_0.1.0_x64-setup.exe`
- **Terminal:** `EnhancedExtract-CLI-0.1.0-beta.1-windows-x64.zip`
- **Verification:** compare your download's SHA-256 with `SHA256SUMS.txt`.

Requires Windows 10 or 11 x64. The desktop app uses WebView2. RAR extraction bundles UnRAR; ISO mounting additionally needs WinFsp and administrator rights. The installer includes the WinFsp installer, but ordinary RAR extraction does not need that driver.

This is a beta. The Windows binaries are unsigned. Test with a disposable copy before enabling source deletion. Automated extraction, recovery, bridge, and build checks passed; the latest installer has not had a complete manual UI retest.

## Right-click extraction

- **Extract with EnhancedExtract:** verifies and extracts into a fresh folder, keeping the archives.
- **Extract and free space:** shows the deletion plan and disk-space estimate before starting.
- **Open with EnhancedExtract:** opens the archive in the dashboard.

Completed files remain on disk after a stopped run. Keep the resume journal beside the archive parts and retain the original output folder, then reopen the set to continue. Early deletion can lose unfinished files after interruption and requires a separate warning acknowledgement. Deleted source parts cannot be restored.

<details>
<summary>See the compact extraction window</summary>

![Explorer extraction](docs/assets/explorer-menu.png)

</details>

## CLI quick start

From the unpacked CLI folder:

```powershell
.\ee-engine.exe --json system check
.\ee-engine.exe --json rar inspect "D:\Downloads\Game.part1.rar" --delete
.\ee-engine.exe --json rar extract "D:\Downloads\Game.part1.rar" --delete --dry-run
```

Review the plan before confirming deletion with `--yes`. Use `--background` for long operations and `jobs status`, `jobs wait`, or `jobs stop` to manage them. `--json schema` lists every command; passwords can be supplied with `--password-stdin`.

## Build and test

See the [build instructions](docs/USER_GUIDE.md#build), [desktop development guide](ui/README.md), and [verification record](docs/SESSION_COMPLETION.md).

```powershell
python -m unittest discover -s tests
cd ui
npm install
npm run build
cd src-tauri
cargo test --lib
```

## License and credits

No open-source license has been chosen; the author's rights are reserved. Bundled third-party components retain their own licenses. See the [credits and license details](docs/USER_GUIDE.md#credits).
