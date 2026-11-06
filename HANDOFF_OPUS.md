# EnhancedExtract Explorer integration handoff

> Historical handoff from an earlier session. Its uncommitted-work and unresolved-menu
> status describes that point in time, not the current branch. The later Explorer work
> was committed as `d8b5007`; current behavior is documented in `README.md` and
> `ui/README.md`. See `docs/SESSION_COMPLETION.md` for this continuation's checks.

Updated 2026-11-06, after the user requested a handoff to Opus.

## Objective and current status

The user wants to right-click a RAR in Explorer and run EnhancedExtract without
opening its dashboard or using an AI agent. They approved the classic Windows 11
"Show more options" menu. The agreed actions are ordinary extraction and extraction
that frees space by deleting used archive parts, with explicit deletion confirmation.

**Not complete:** the implementation builds and extraction works in the installed
compact launcher, but the two commands have not appeared in the actual Explorer
context menu. Do not claim the right-click feature works yet. Restarting Explorer
did NOT resolve this. Root cause remains unknown.

The user explicitly approved one Explorer restart, which was performed in the latest
turn. Computer Use was subsequently stopped by the physical Escape key. The user
then requested this handoff. No more UI actions were taken after that stop.

## Workspace and changes

Repository: `C:\Kuliah\Vibe Coding\EnhancedExtract`

All feature edits are uncommitted in the current checkout. No branch or commit was
created. Existing untracked `videos/` belongs to earlier work; leave it alone.

Changed / added files:

- `ui/src-tauri/src/shell.rs`: parses `--shell-extract <rar>` and
  `--shell-extract-delete <rar>`; normalizes later `.partN.rar` to the first volume;
  chooses numbered output folders; atomically reserves new output directories;
  normalizes canonical Windows device paths for UnRAR/Explorer; holds a per-archive
  Windows file-handle lock while the compact window is open. Includes three tests.
- `ui/src-tauri/src/lib.rs`: exposes `shell_request`, `shell_destination`, and
  `open_output`; configures a smaller native-decorated window for shell mode;
  acquires the per-archive launcher lock. Reuses the existing engine bridge.
- `ui/src-tauri/tauri.conf.json`: starts the window hidden until frontend bootstrap;
  connects NSIS `windows/hooks.nsh`.
- `ui/src-tauri/capabilities/default.json`: adds the window-show permission.
- `ui/src-tauri/windows/hooks.nsh`: installer registration and uninstaller cleanup.
- `ui/src/main.tsx`: chooses dashboard or compact launcher from `shell_request`, then
  shows the window. An invalid shell request produces a visible error.
- `ui/src/QuickExtract.tsx` and `ui/src/quick-extract.css`: standalone extraction UI.
- `ui/README.md`: documents behavior, flags, installation, and verification.

The Python extraction engine, CLI, and existing dashboard behavior were reused;
their source was not changed by this task. ZIP support was not added.

## Implemented behavior

Ordinary mode runs an engine dry-run, reserves a fresh folder beside the archive,
then starts verification and extraction as a detached engine job. It keeps all RAR
parts. Existing output is preserved with `Game (2)`, `Game (3)`, etc.

Delete mode shows the real engine dry-run steps, output folder, required/free space,
an expandable list of the exact parts to delete, a warning, and a required checkbox.
Only the user's explicit confirmation sends `--yes`. Verification remains enabled.
Canceling this screen changes no archive or output folder.

Both modes handle archive passwords via stdin, show progress/errors, allow opening
completed output, and require confirmation before stopping a running extraction.
Closing the window leaves the background job running. Jobs remain available in the
main dashboard's Jobs screen. A reopened running extraction attempts to attach to
its existing job. Passwords are not put on command lines or in stored job arguments.

## Installed artifacts and registration

Built installer:

`ui\src-tauri\target\release\bundle\nsis\EnhancedExtract_0.1.0_x64-setup.exe`

Built application:

`ui\src-tauri\target\release\enhancedextract-ui.exe`

Installed application:

`C:\Users\Sibgha\AppData\Local\EnhancedExtract\enhancedextract-ui.exe`

Installed engine:

`C:\Users\Sibgha\AppData\Local\EnhancedExtract\engine\ee-engine.exe`

The installer is current-user NSIS. Intended keys currently restored to match source:

```
HKCU\Software\Classes\*\shell\EnhancedExtract
    (Default) = Extract with EnhancedExtract
    Icon = <installed exe>,0
    MultiSelectModel = Single
    AppliesTo = System.FileExtension:=.rar
    command\(Default) = "<installed exe>" --shell-extract "%1"

HKCU\Software\Classes\*\shell\EnhancedExtractFree
    (Default) = Extract and free space with EnhancedExtract...
    Icon = <installed exe>,0
    MultiSelectModel = Single
    AppliesTo = System.FileExtension:=.rar
    command\(Default) = "<installed exe>" --shell-extract-delete "%1"
```

`NSIS_HOOK_POSTUNINSTALL` removes only these two owned keys. Postinstall also removes
the earlier owned `SystemFileAssociations\.rar\shell` prototype keys.

The source uses single-quoted NSIS strings containing plain double quotes for the
command. An earlier incorrect `$"` form wrote literal dollar signs; that was fixed,
rebuilt, reinstalled, and actual registry command quoting was verified afterward.
Do not reintroduce that error.

## Verification evidence

Successful checks already run against this implementation:

- `npm run build` in `ui`: TypeScript + Vite passed.
- `cargo test --lib` in `ui/src-tauri`: 6 tests passed (3 existing bridge tests and
  3 new shell tests). Tests exercise padded/unpadded first-part resolution, Unicode
  names, ordinary/UNC path normalization, invalid arguments, directory reservation,
  preserving existing output, and exclusive launcher file handles on Windows.
- `python -m unittest discover -s tests` from repository root: 20 tests passed.
- `npm run tauri build`: installer built successfully, including the NSIS hooks.
- Installed launcher was run with the bundled engine, without `EE_ENGINE` override.
  It selected part 2 of a 5-part RAR, resolved part 1, verified/extracted successfully,
  and displayed 100% completion. Extracted payload SHA-256 matched the original.
- All five source parts remained, and a pre-existing `Demo/keep.txt` was unchanged.
- Password-protected extraction completed through the compact password prompt;
  extracted payload hash matched. The test password was absent from stored job argv.
- Open folder opened the correct output directory in Explorer.
- Deletion-plan screen was inspected with the destructive action disabled until
  acknowledgement. Closing/canceling left all parts intact and created no planned
  output directory. The new compact UI's destructive confirmation was NOT executed
  during manual UI tests. Existing engine tests cover destructive extraction.

Early packaged extraction failed because `canonicalize()` returned a `\\?\` device
path that UnRAR rejected. `ordinary_path()` fixed this, and installed extraction
was rerun successfully. Preserve this fix.

Vite emitted nonfatal static/dynamic import bundling notices. Tauri emitted its
pre-existing warning about the bundle identifier ending in `.app`.

## Smoke-test fixtures

Disposable fixture directory:

`C:\Users\Sibgha\AppData\Local\Temp\ee-shell-smoke-qw0imkgw\RAR demo ü`

- `Demo.part1.rar` through `Demo.part5.rar`: 1.1 MB random payload, five volumes.
- `Secret.rar`: encrypted-header fixture; test password is `fixture-password`.
- `payload.txt`: original random binary payload, despite the filename extension.
- `Demo/keep.txt`: pre-existing output sentinel.
- `Demo (2)`: leftover empty output from the early device-path failure.
- `Demo (3)`: successful installed extraction.
- `Secret`: successful encrypted extraction.
- `Engine check`: direct engine smoke-test output.
- `installed-jobs` and `jobs-data`: isolated test job/log directories.
- `verification.json`: saved hashes, preservation checks, registration, latest
  unresolved Explorer visibility status.
- `smoke-input.json`: input paths from the initial test setup.

These fixtures were initially created with absolute source paths in Rar.exe, so the
archive contains nested `Users/.../payload.txt` paths. Locate extracted payloads
recursively. This nesting is fixture content, not an extraction regression.

The temporary repository `build/shell-smoke.json` was removed after moving evidence
into the fixture directory. Test data was not mixed into the user's normal jobs.

## Unresolved Explorer menu investigation

The following are evidence, not proof of a root cause:

1. The owned keys are visible through HKCU and the merged HKCR view. Both 32-bit and
   64-bit registry views were checked. The executable and icon path exist.
2. `shlwapi.AssocQueryStringW(0, ASSOCSTR_COMMAND, ".rar", "EnhancedExtract", ...)`
   resolves the correct command successfully. This proves lookup, not menu visibility.
3. Explorer and the tool process have the same user SID:
   `S-1-5-21-2083654924-2017901367-2071027399-1001`.
4. `NtQueryKey` resolves both EnhancedExtract and the working ShareX entry into the
   same real `<SID>_Classes\*\shell` hive. Their inherited registry access entries
   match; only the owner differs (user vs Administrators).
5. `GetCurrentPackageFullName` in the tool's Python returns 15700 (no package).
   The suspected Codex/MSIX package isolation was NOT established and must not be
   presented as the explanation.
6. Explorer's real classic RAR and TXT menus show WinRAR, 7-Zip, ShareX and other
   existing commands, but did not show either EnhancedExtract action.
7. An approved Explorer restart was performed using session-scoped process restart.
   The taskbar and Explorer restarted; visibility remained unresolved.
8. Installer was also invoked using `Shell.Application.ShellExecute(..., '/S', ...)`
   through the native shell. This did not establish visible menu entries either.
9. Temporary probes included removing AppliesTo/MultiSelectModel, explicit MUIVerb
   and Position, quoted Icon, another label, direct WinRAR ProgID registration, and
   a minimal static diagnostic verb (including a known Windows executable).
   Observations still did not show the new entries. Some UI attempts returned stale
   state / physical-user-input invalidation, so don't treat every probe as a perfectly
   controlled elimination.
10. The very last probe added an owned AllFilesystemObjects static verb, but Computer
    Use was stopped before it could be observed. It was removed during handoff cleanup.
    Its behavior is unknown.

All temporary diagnostics were removed during handoff: `EERegistrationCheck`, the
owned WinRAR ProgID entry, and the owned AllFilesystemObjects entry. The two intended
wildcard keys were restored to the exact installer values above. No global Explorer,
security, default-association, or third-party application settings were changed.

## Continuation guidance

- Resolve actual Explorer visibility before declaring completion. Another blind
  extraction run or another registry-read success will not prove the right-click flow.
- Prefer a small controlled diagnostic over repeating all probes. Investigate how
  Explorer enumerates the new static verb versus the working ShareX registration.
  The current evidence does not justify blaming caching, package isolation, or policy.
- Once visible, launch ordinary extraction from the actual menu and verify output;
  confirm the free-space menu opens the plan and still requires explicit consent.
- Rebuild/reinstall if source changes. Keep installed behavior aligned with the final
  source. Avoid leaving global unfiltered diagnostic actions behind.
- Follow `AGENTS.md`: drive engine operations through `cli.py`; never add destructive
  `--yes` to an agent-run archive operation without the required plan and user approval.
- Read both computer-use and laya-computer-use skills before new Windows UI work.
  Do not resume Computer Use in the turn that was stopped by Escape.
- No external messages, publication, commits, or pushes have been made.
