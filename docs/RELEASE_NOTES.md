# EnhancedExtract 0.1.0

Windows archive extraction for tight disk space, with a desktop dashboard, Explorer integration and a standalone CLI.

The desktop app uses Tauri and Rust, with a React interface and a bundled Python engine.

- Extract ZIP, 7z, TAR, GZ, BZ2, XZ, ZST, CAB, WIM and split archives through bundled 7-Zip.
- Verify multipart RAR sets, estimate space, and resume safe deletion from the parts left.
- Extract compressed TAR files directly without writing an intermediate TAR.
- Start extraction from the Library, by dropping an archive, or from the Explorer submenu.
- Follow background jobs after closing the extraction window.
- Use the standalone CLI without installing Python, WinRAR or 7-Zip.
- Install from UDF ISOs with the experimental ISO workflow.

## Downloads

- `EnhancedExtract_0.1.0_x64-setup.exe`: Windows desktop installer, bundled engine and Explorer integration.
- `EnhancedExtract-CLI-0.1.0-windows-x64.zip`: unpack the whole folder and run `ee-engine.exe --cli --help`.
- `SHA256SUMS.txt`: SHA-256 checksums for the installer, CLI ZIP and notices.
- `THIRD_PARTY_NOTICES.txt`: bundled component notices and licences.

Windows 10/11 x64. The desktop app requires WebView2. Archive extraction needs no administrator rights. ISO installation additionally requires WinFsp and administrator rights.

## Deletion and resume

Extraction keeps source files unless you choose deletion. For ZIP, 7z, TAR and other non-RAR formats, the archive is deleted only after extraction completes cleanly. These formats require room for the unpacked files and retry from the beginning after a stop.

RAR safe mode retains parts needed by unfinished files and records a resume journal. Solid sets and very large files can still require room for the whole output. RAR early deletion can lose the file being extracted after a stop or crash, and requires a separate confirmation.

ISO space freeing remains experimental. Use disposable data to evaluate source-deletion modes.

## Verification and limits

46 Python tests passed through the source CLI and through the packaged engine, with no skips. Eight Rust tests, the TypeScript/Vite build, the engine build and the Windows installer build passed. Tests include real encrypted and multipart archives, corrupt-archive retention, RAR interruption/resume, CAB, WIM and Zstandard, plus ISO mount/read/unmount.

The Windows binaries are unsigned. Windows may display an unknown-publisher or SmartScreen warning. Compare the download with `SHA256SUMS.txt` before running it.

Windows 11 Explorer entries belong in **Show more options**. Shell parsing and installer compilation were tested; menu visibility on a fresh Windows installation has not been manually verified for this release. Not every legacy archive format or compression method has a test fixture.

No open-source licence has been selected for EnhancedExtract. The author's rights and bundled third-party licences remain unchanged.
