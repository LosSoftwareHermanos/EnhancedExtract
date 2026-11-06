"""Package an already-built Windows installer and CLI: python build/package-release.py."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    config = json.loads((ROOT / "ui/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    version = config["version"]
    engine = ROOT / "build/dist/ee-engine"
    installer = ROOT / f"ui/src-tauri/target/release/bundle/nsis/EnhancedExtract_{version}_x64-setup.exe"
    notices = ROOT / "docs/THIRD_PARTY_NOTICES.txt"
    for path in (installer, engine / "ee-engine.exe", engine / "_internal/7zip/7z.exe", notices):
        if not path.is_file():
            raise SystemExit(f"Missing release input: {path}")
    output = ROOT / f"build/dist/release-{version}"
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(installer, output / installer.name)
    shutil.copy2(notices, output / notices.name)
    cli_name = f"EnhancedExtract-CLI-{version}-windows-x64"
    cli_zip = output / f"{cli_name}.zip"
    with zipfile.ZipFile(cli_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(engine.rglob("*")):
            if path.is_file():
                archive.write(path, f"{cli_name}/{path.relative_to(engine).as_posix()}")
        archive.write(notices, f"{cli_name}/THIRD_PARTY_NOTICES.txt")
        archive.writestr(f"{cli_name}/GETTING_STARTED.txt", f"""EnhancedExtract {version} for Windows x64

Unpack this whole folder before running the CLI. Keep _internal beside ee-engine.exe.
Python, UnRAR and 7-Zip are included; no separate Python installation is required.

Examples from PowerShell in this folder:
  .\\ee-engine.exe --cli --help
  .\\ee-engine.exe --cli --json system check
  .\\ee-engine.exe --cli --json scan D:\\Downloads
  .\\ee-engine.exe --cli --json archive inspect D:\\Downloads\\Pack.zip
  .\\ee-engine.exe --cli --json archive extract D:\\Downloads\\Pack.zip --dry-run
  .\\ee-engine.exe --cli --json archive extract D:\\Downloads\\Pack.zip

The last command keeps the source archive. Review a --delete --dry-run plan before
confirming deletion with --yes. Incremental deletion and journal resume apply only
to RAR. Other formats retain all source parts until extraction completes cleanly.

ISO installation additionally needs WinFsp and administrator rights. ISO space
freeing is experimental. See the user guide before using it.

User guide: https://github.com/gustavofring1483369/EnhancedExtract/blob/v{version}/docs/USER_GUIDE.md
Issues: https://github.com/gustavofring1483369/EnhancedExtract/issues
Third-party licences: THIRD_PARTY_NOTICES.txt
""")
    assets = [output / installer.name, cli_zip, output / notices.name]
    hashes = []
    for path in assets:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        hashes.append(f"{digest}  {path.name}\n")
        print(f"{path.name}: {path.stat().st_size} bytes, SHA-256 {digest}")
    (output / "SHA256SUMS.txt").write_text("".join(hashes), encoding="utf-8", newline="\n")
    print(f"Release assets: {output}")


if __name__ == "__main__":
    main()
