# EnhancedExtract for agents

Drive the app through `cli.py`, not the window. It never prompts: every input is a flag.
`python cli.py --json schema` returns every command, flag, example and exit code in one
JSON document (about 10 KB); `python cli.py <group> <command> --help` shows one command.

## The loop

```
python cli.py --json scan D:\Downloads                         # find RAR sets / ISOs; each has "next"
python cli.py --json rar inspect D:\Downloads\Game.part1.rar   # sizes, free space, "next"
python cli.py --json rar extract D:\Downloads\Game.part1.rar --delete --dry-run   # the plan
#   show the plan to the user; only with their OK:
python cli.py --json rar extract D:\Downloads\Game.part1.rar --delete --yes --background
python cli.py --json jobs wait --timeout 60      # repeat while exit code is 7
```

Every inspect, dry run and job result carries `next`: the command to run next. Long
commands (`rar verify`, `rar extract`, `iso install`) take `--background`: they return a job
id at once, keep running after your tool call ends, and are followed with
`jobs status|wait|logs|stop`. The job id can be left out (newest job) or shortened.

```
python cli.py --json system check | install-winfsp [--dry-run] | install-fusepy [--dry-run]
python cli.py --json scan FOLDER [--depth N]
python cli.py --json rar inspect|verify|extract ARCHIVE [--dest DIR] [--delete] [--dry-run] [--yes] [--background]
python cli.py --json iso inspect ISO [--install-size-mb N] [--files]
python cli.py --json iso install ISO --install-dir DIR --install-size-mb N --silent [--dry-run] [--yes] [--background]
python cli.py --json iso install ISO --no-free --no-setup --background   # mount only; `jobs stop` unmounts
python cli.py --json iso delete ISO [--dry-run] [--yes]
python cli.py --json jobs list | status [ID] | wait [ID] [--timeout S] | logs [ID] [--tail N] [--type T..] | stop [ID] [--force]
```

The frozen exe takes the same arguments after `--cli`: `EnhancedExtract.exe --cli --json schema`.

## Output contract

- `--json` (anywhere on the line, or `EE_JSON=1`): every stdout line is one JSON object with
  `type` and `ts`. The last line is always
  `{"type": "result", "ok": ..., "exit_code": ..., "schema": 2, "duration_s": ...}` plus the
  command's data. Read only that line if you only need the outcome.
- Output stays small: progress at most every 2 s (`--progress-every S`) with `overall` %,
  `eta_s` and `files_done`; UnRAR's one-line-per-file output is counted, not printed
  (`--verbose` prints it). ISO status lines appear only when something changed (or once a
  minute).
- Failures carry `error` and usually `fix`: a command line that gets past the problem.
- Text mode: data and the final `key: value` lines go to stdout; progress, logs, warnings
  and errors go to stderr. `-q` hides progress.
- Passwords: `--password-stdin` (preferred), `EE_PASSWORD`, or `--password` (visible to
  other programs). Background jobs get the password through their environment, never their
  command line.
- Flags must be written in full (`--dry-run`, not `--dry`).

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
| 7 | job still running (`jobs wait` timed out) | wait again |
| 130 | Ctrl+C / `jobs stop` | |

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
  `--install-dir`. `jobs stop` while setup runs only warns; `jobs stop --force` unmounts
  anyway (setup then fails, and when freeing, the ISO is lost).
- Jobs and logs live in the data folder (`EE_DATA_DIR` overrides it).

Tests: `python -m unittest discover -s tests` (RAR tests need WinRAR; the ISO job test
needs WinFsp and fusepy).
