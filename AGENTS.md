# EnhancedExtract for agents

Drive the app through `cli.py`, not the window. It never prompts: every input is a flag.
Start with `python cli.py`, then `python cli.py <group> <command> --help` (each has Examples).

```
python cli.py --json system check
python cli.py --json system install-winfsp [--dry-run]
python cli.py --json rar inspect ARCHIVE [--dest DIR] [--delete]
python cli.py --json rar verify  ARCHIVE
python cli.py --json rar extract ARCHIVE [--dest DIR] [--delete] [--dry-run] [--yes]
python cli.py --json iso inspect ISO [--install-size-mb N] [--files]
python cli.py --json iso install ISO --install-dir DIR --install-size-mb N [--silent] [--dry-run] [--yes]
python cli.py --json iso install ISO --no-free --no-setup      # mount only; send "quit" on stdin
python cli.py --json iso delete  ISO [--dry-run] [--yes]
```

The frozen exe takes the same arguments after `--cli`: `EnhancedExtract.exe --cli --json system check`.

## Output contract

- `--json` (anywhere on the line, or `EE_JSON=1`): every stdout line is one JSON object with
  `type` and `ts`. The last line is always
  `{"type": "result", "ok": ..., "exit_code": ..., "schema": 1, "duration_s": ...}` plus the
  command's data.
- Failures carry `error` and usually `fix`: a command line that gets past the problem.
- Text mode: data and the final `key: value` lines go to stdout; progress, logs, warnings
  and errors go to stderr. Add `-q` to hide progress.
- Passwords: `--password-stdin` (preferred), `EE_PASSWORD`, or `--password` (visible to
  other programs).

## Exit codes

| code | meaning | what to do |
|---|---|---|
| 0 | success, or already done (`already_done: true`) | |
| 1 | job failed | read `error` |
| 2 | bad arguments or input | run `fix` |
| 3 | password needed or wrong | ask the user for the password |
| 4 | not enough free space | report `needed` and `free` |
| 5 | missing UnRAR, WinFsp, fusepy or admin rights | run `system check`, follow the `hint` events |
| 6 | destructive step needs `--yes` | show the user, then run `fix` (same command + `--yes`) |
| 130 | Ctrl+C | |

## Rules

- Never add `--yes` on your own. It confirms data loss: deleting RAR parts, freeing the
  ISO while setup reads it, or deleting the ISO. Run with `--dry-run` first, show the user
  the `plan`, and get their OK.
- Retrying is safe: a finished `rar extract --delete` or `iso delete` reports
  `already_done` instead of failing.
- The install size (`--install-size-mb`) comes from setup's "At least ... MB of free disk
  space is required"; ask the user for it.
- `iso install` runs setup.exe and needs an administrator terminal, plus WinFsp and
  `pip install fusepy`. `--silent` runs an Inno Setup installer unattended into
  `--install-dir`. It blocks until setup exits, so run it in the background and read its
  events.

Tests: `python -m unittest discover -s tests` (the RAR tests need WinRAR).
