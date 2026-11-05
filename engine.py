"""Entry point of ee-engine.exe, the engine the Tauri UI runs: the JSON CLI without the Tk app.

    ee-engine.exe --cli --json <command ...>   the CLI (cli.py); `--cli` is optional
    ee-engine.exe --vdrive ...                 the virtual drive process (vdrive.py)
"""
import sys

if __name__ == "__main__":
    if sys.argv[1:2] == ["--vdrive"]:
        del sys.argv[1]
        import vdrive
        vdrive.main()
        sys.exit(0)
    if sys.argv[1:2] == ["--cli"]:
        del sys.argv[1]
    import cli
    sys.exit(cli.main())
