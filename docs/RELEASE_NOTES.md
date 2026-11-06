# EnhancedExtract 0.1.0 beta 1

Windows archive extraction for tight disk space, with Explorer integration, a desktop
dashboard, and a standalone CLI.

The desktop app uses Tauri and Rust, with a React interface and a bundled Python engine.

- Multipart RAR extraction with verification, disk-space estimates, and resumable deletion.
- Compact right-click extraction; open the dashboard when you want more options.
- Standalone CLI ZIP with Python and UnRAR bundled.
- Experimental ISO installation and space-freeing workflow.

## Downloads

- `EnhancedExtract_0.1.0_x64-setup.exe`: Windows desktop installer and Explorer integration.
- `EnhancedExtract-CLI-0.1.0-beta.1-windows-x64.zip`: unpack and run `ee-engine.exe`.
- `SHA256SUMS.txt`: SHA-256 checksums for the downloads.
- `THIRD_PARTY_NOTICES.txt`: bundled component notices.

## Beta limitations

Windows 10/11 x64. Desktop use requires WebView2. ISO mounting also requires WinFsp and
administrator rights. Windows 11 Explorer entries are under **Show more options**.
The binaries are unsigned; signing and a complete manual retest of the latest installer
remain outstanding.

Safe deletion retains parts needed by unfinished files. Solid archives or very large files
can need room for the whole output. Early deletion can lose unfinished files after a stop
or crash. Test with disposable data before enabling source deletion. ZIP and 7z extraction
are not supported.

No open-source license has been selected for EnhancedExtract. Third-party components
retain their own licenses.

## Verification

26 Python tests and 6 Rust tests passed. TypeScript/Vite, the engine build, and the Windows
installer build passed. The packaged engine passed 19 CLI/RAR tests. The release CLI ZIP
was unpacked into a fresh directory and checked with a real RAR extraction, output hash
comparison, and source-preservation check. All release checksums were verified.
