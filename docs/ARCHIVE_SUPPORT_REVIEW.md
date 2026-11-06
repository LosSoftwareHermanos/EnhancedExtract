# Archive support completion review

> Historical work record before the 0.1.0 release. See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the current distributed version.

Verified 6 November 2026. Changes remain uncommitted. No release was published.

## Recovered session

Claude chat: **Zip and 7-zip compression support**.
Session ID: `3b2d7cee-c742-4427-b5d4-771d71115293`.

The request was to add ZIP, 7z and other common compression formats. The session implemented the 7-Zip engine, CLI routing, archive screens and installer integration. It stopped at the usage limit while reviewing the README.

## Checklist

- [x] Explore codebase archive handling. Reviewed the engine, CLI, job flow, UI, build recipes and shell integration.
- [x] Design multi-format support. RAR retains UnRAR and its safe/early deletion and resume behavior. Other formats use 7-Zip, retain their archives during extraction, and support deletion after clean completion.
- [x] Implement ZIP/7z/TAR/etc. extraction. Completed the existing implementation and fixed compressed-TAR handling and missing-part reporting.
- [x] Update UI, CLI and site copy. ZIP stop messages no longer promise RAR-style resume. Documentation and the site distinguish the new source/local builds from published beta 1 downloads. Installer registration includes the supported single-file extensions.
- [x] Test with real archives. Source and packaged CLI suites both pass, and the desktop installer builds.

## Fixes made during this continuation

- `.tgz`, `.tar.bz2` and `.txz` could return success while writing an intermediate TAR instead of extracting its files. TAR detection now uses the archive name as well as the stored member name, and checks the actual compressor type.
- 7-Zip listings of raw BZ2/XZ/Zstandard streams may omit `Path`. The parser now reads these entries. Unknown unpacked sizes are measured through a bounded-memory stream before the free-space check; compressed TARs use their member sizes when necessary. Inspecting these archives can therefore require a decompression pass.
- Reading nested TAR contents now checks both pipeline exit codes instead of silently accepting a failed listing.
- Scanning classic split ZIP sets now flags gaps such as `.z01`, `.z03`, `.zip` missing part 2.
- ZIP stop confirmation retains the archive and extracted files without offering journal-based resume. The dashboard identifies non-RAR jobs from the archive path even before the first progress event.
- Installer add/remove hooks now also cover `.z`, `.arj`, `.lzh`, `.lha` and `.cpio`.
- Added regression and integration coverage for these behaviors, WIM, CAB, Zstandard, background ZIP jobs and fallback to the bundled 7-Zip without a system installation.

## Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 46 passed, no skips |
| Same suite with `EE_TEST_ENGINE` pointing to `build/dist/ee-engine/ee-engine.exe` | 46 passed, no skips |
| `cargo test --lib`, from `ui/src-tauri` | 8 passed |
| `npm run build`, from `ui` | TypeScript check and Vite production build passed |
| PyInstaller `ee-engine.spec` build | Passed |
| `npm run tauri build`, from `ui` | Release executable and NSIS installer built |
| NSIS contents | Contains `engine/ee-engine.exe`, `7z.exe`, `7z.dll` and `License.txt` |
| `git diff --check` | Passed |
| Documentation Unicode audit | No suspicious characters reported |

Real-file tests compare extracted bytes with their source payloads. Covered formats include ZIP, encrypted ZIP, 7z, encrypted 7z, split 7z, TAR, TAR.GZ/TGZ, TAR.BZ2, TXZ, GZ, BZ2, XZ, ZST, TAR.ZST, WIM and a CAB produced by Windows `makecab`. Existing RAR corruption/deletion/resume and ISO background mount/read/unmount tests also pass. Tests use their own temporary archives and isolated job data.

To repeat the suite through the packaged engine from the repository root:

```powershell
$env:EE_TEST_ENGINE = (Resolve-Path 'build/dist/ee-engine/ee-engine.exe').Path
try { python -m unittest discover -s tests -v }
finally { Remove-Item Env:EE_TEST_ENGINE }
```

Final test/build logs are in `%TEMP%/ee-archive-final-tests.log`, `%TEMP%/ee-archive-packaged-tests.log`, `%TEMP%/ee-archive-engine-build.log` and `%TEMP%/ee-archive-tauri-build.log`.

## Local artifacts and remaining limits

- Engine: `build/dist/ee-engine/ee-engine.exe`.
- Desktop executable: `ui/src-tauri/target/release/enhancedextract-ui.exe`.
- Installer: `ui/src-tauri/target/release/bundle/nsis/EnhancedExtract_0.1.0_x64-setup.exe`.
- Landing-page visual/interaction checks are recorded separately in [LANDING_PAGE_REVIEW.md](LANDING_PAGE_REVIEW.md). This continuation subsequently updated only its format-support wording.

The installer was built and inspected, but was not installed over the user's existing app. Windows Explorer menu visibility was not retested. Shell parsing, destination handling and installer compilation passed; these do not establish that Explorer displays the menu on this machine. The tests do not cover every legacy archive type or every compression method accepted by 7-Zip. Classic split ZIP gap detection was tested by filename; the real multipart extraction fixture uses split 7z.

Beta 1 release assets remain unchanged. ZIP/7z/TAR support is available in this source checkout and the new local build, not in those older downloads. The existing private-repository download restriction and experimental ISO space-freeing limits remain documented in the landing-page review.
