# Contributing to EnhancedExtract

Thanks for helping. Bug reports, fixes, tests, docs and translations of the UI copy are all welcome.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug.** Open an [issue](https://github.com/LosSoftwareHermanos/EnhancedExtract/issues/new/choose) with the version, Windows version, archive format and number of parts, and what you expected. Add the job log from the Jobs screen or `logs/` if you can.
- **Suggest a feature.** Use the feature request template and describe the problem first, then your idea.
- **Fix something.** Issues labelled `good first issue` are a good start. For anything larger than a small fix, open an issue first so we can agree on the approach before you spend time on it.
- **Security problems** go through [private vulnerability reporting](SECURITY.md), not public issues.

## Project layout

| Part | Where | Tech |
|---|---|---|
| Engine and CLI | `*.py` at the root (`cli.py`, `extractor.py`, `sevenzip.py`, `isocore.py`, `vdrive.py`, ...) | Python 3, no runtime dependencies except `fusepy` for ISO installs |
| Desktop app | `ui/src` (React + TypeScript), `ui/src-tauri` (Rust) | Tauri 2, Vite |
| Windows installer | `ui/src-tauri/windows/` | NSIS template, skin and pages |
| Landing page | `site/` | Static HTML/CSS/JS on Cloudflare Pages |
| Tests | `tests/` | `unittest` |

The app never touches archives itself: it runs the engine's JSON CLI (`cli.py --json`) and reads the result. [AGENTS.md](AGENTS.md) describes that CLI contract, and the README's CLI section lists every command.

## Set up

You need Windows 10 or 11 (x64).

```powershell
git clone https://github.com/LosSoftwareHermanos/EnhancedExtract.git
cd EnhancedExtract

# Engine: Python 3.11 or newer, nothing to install for archives
python cli.py --json system check

# Desktop app (needs Node 20+ and Rust stable)
cd ui
npm ci
npm run tauri dev
```

For RAR tests install WinRAR (the tests build archives with `Rar.exe`). 7-Zip (`7z.exe` on PATH or in `deps/7zip`) covers the other formats. ISO tests need WinFsp and `python -m pip install fusepy`. Tests that need a missing tool are skipped, not failed.

## Before you open a pull request

Run what applies to your change:

```powershell
python -m unittest discover -s tests          # engine and CLI
cd ui; npm run typecheck; npm run build       # desktop UI
cd ui/src-tauri; cargo test                   # Rust shell
```

GitHub Actions runs the same checks on every pull request.

Please also:

- **Keep pull requests focused.** One fix or feature per PR, with a short description of what changed and how you tested it.
- **Add or update tests** for engine behaviour, especially anything that deletes files.
- **Keep the CLI scriptable.** Every input is a flag, nothing prompts, `--json` output stays one object per line, and destructive steps still need `--yes` (see AGENTS.md).
- **Update the docs** (README, `docs/USER_GUIDE.md`, `--help` text) when you change behaviour or flags.
- **Don't commit build output** (`build/dist`, `ui/dist`, `ui/src-tauri/target`, installers). Releases are built by the maintainer.

## Building a release (maintainers)

```powershell
build\build-engine.bat                        # engine -> build/dist/ee-engine
cd ui; npx tauri build --bundles nsis         # installer
python build/package-release.py               # release files and SHA256SUMS
```

Bump the version in `cli.py`, `ui/package.json`, `ui/src-tauri/Cargo.toml` and `ui/src-tauri/tauri.conf.json`, add a section to `docs/RELEASE_NOTES.md`, then tag `vX.Y.Z` and attach the files from `build/dist/release-X.Y.Z` to a GitHub release.

## Licence of contributions

EnhancedExtract is under the [MIT License](LICENSE). By submitting a contribution you agree that it is licensed under the same terms. Don't add code or assets you don't have the right to share under MIT-compatible terms; note any third-party licence in `docs/THIRD_PARTY_NOTICES.txt`.
