"""EnhancedExtract for the terminal: the same jobs as the window, driven by flags, so
scripts and AI agents can run them end to end without prompts.

Run `python cli.py` to see the commands, and `python cli.py <group> <command> --help` for
each one's flags and examples. See AGENTS.md for the JSON contract.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time

import extractor as ex
import isocore as iso
import jobs
import paths
import sevenzip as sz
import udf

VERSION = "0.1.3"
SCHEMA = 2          # bumped when JSON event fields change incompatibly

EXIT = {
    0: "success (or already done)",
    1: "the job failed",
    2: "bad arguments or input",
    3: "password needed or wrong",
    4: "not enough free space",
    5: "something the PC needs is missing (UnRAR, 7-Zip, WinFsp, fusepy, admin rights)",
    6: "a destructive step needs --yes",
    7: "the job is still running (jobs wait timed out); wait again",
    130: "stopped with Ctrl+C",
}
SETUP_SILENT = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
DONE_MARKER = ".enhancedextract-done.json"      # left in the destination by `archive extract --delete`
PROG = f"{os.path.basename(sys.executable)} --cli" if paths.FROZEN else "python cli.py"

# Text mode: these event types are the command's data and go to stdout; everything else
# (progress, logs, warnings, errors) goes to stderr so stdout can be piped.
DATA_TYPES = {"archive", "space", "iso", "file", "check", "plan", "job", "job_event", "rar_set", "archive_set",
              "found_iso"}
CHATTY_TYPES = {"log", "progress", "status", "event"}      # hidden by --quiet


class Stop(Exception):
    """Ends the command with an exit code. `fix` is a command that would get past it."""

    def __init__(self, code, msg, fix=None, **extra):
        super().__init__(msg)
        self.code, self.msg, self.fix, self.extra = code, msg, fix, extra


class Out:
    """Writes events as JSON lines (--json) or as plain text."""

    def __init__(self, as_json=False, quiet=False):
        self.as_json = as_json
        self.quiet = quiet
        self.lock = threading.Lock()

    def __call__(self, type, msg=None, **fields):
        with self.lock:
            if self.as_json:
                obj = {"type": type, "ts": round(time.time(), 3)}
                if msg is not None:
                    obj["msg"] = msg
                obj.update(fields)
                print(json.dumps(obj, ensure_ascii=False), flush=True)
                return
            if msg is None or (self.quiet and type in CHATTY_TYPES):
                return
            prefix = {"error": "Error: ", "warning": "Warning: ", "hint": "Hint: "}.get(type, "")
            print(prefix + msg, file=sys.stdout if type in DATA_TYPES else sys.stderr, flush=True)

    def result(self, code, fields):
        if self.as_json:
            self("result", None, exit_code=code, schema=SCHEMA, **fields)
            return
        # Plain "key: value" lines on stdout, easy to read and to grep.
        for key, value in fields.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            print(f"{key}: {value}")


def command_line(argv, *extra):
    return subprocess.list2cmdline(PROG.split() + list(argv) + list(extra))


def with_yes(args):
    """The command the user ran, with --yes added: what to rerun once they agree."""
    return command_line(args.argv, *([] if "--yes" in args.argv else ["--yes"]))


# ---------- background jobs ----------
def start_background(args, out):
    """Re-run this command detached; return its job id at once."""
    argv, skip = [], False
    for a in args.argv:
        if skip:
            skip = False
        elif a == "--password":
            skip = True
        elif a not in ("--background", "--json", "--password-stdin", "-q", "--quiet") \
                and not a.startswith("--password="):
            argv.append(a)
    job_id = jobs.start(argv, password=getattr(args, "pw", None))
    out("event", f"Started background job {job_id}.", job=job_id)
    return {"ok": True, "job": job_id, "state": "running",
            "next": command_line(["jobs", "wait", job_id, "--timeout", "60"])}


def find_job(args):
    job_id = jobs.resolve(args.id)
    if not job_id:
        raise Stop(2, f"No job matches {args.id!r}." if args.id else "There are no jobs yet.",
                   fix=f"{PROG} jobs list")
    return job_id


def job_result(snap):
    """A job snapshot as this command's result; exit code 7 while it is still running."""
    code = {"running": 7, "done": 0, "died": 1}.get(snap["state"], snap.get("job_exit_code") or 1)
    if snap["state"] == "running":
        snap["next"] = command_line(["jobs", "wait", snap["id"], "--timeout", "60"])
    return code, dict(snap, ok=snap["state"] in ("running", "done"))


def job_line(snap):
    p = snap.get("progress", {})
    where = (p.get("msg") or "") if p else ""
    return f"{snap['id']}  {snap['state']:<7} {snap['elapsed_s']:>7}s  {snap['command']}" + (f"  [{where}]" if where else "")


def cmd_jobs_list(args, out):
    snaps = [jobs.snapshot(i) for i in jobs.ids()[:args.limit]]
    for s in snaps:
        out("job", job_line(s), **s)
    return {"ok": True, "jobs": len(snaps), "running": sum(s["state"] == "running" for s in snaps)}


def cmd_jobs_status(args, out):
    snap = jobs.snapshot(find_job(args))
    out("job", job_line(snap))
    return job_result(snap)


def cmd_jobs_wait(args, out):
    job_id = find_job(args)
    deadline = time.time() + args.timeout
    while True:
        snap = jobs.snapshot(job_id)
        if snap["state"] != "running" or time.time() >= deadline:
            break
        time.sleep(0.5)
    out("job", job_line(snap))
    return job_result(snap)


def cmd_jobs_logs(args, out):
    job_id = find_job(args)
    evs = [e for e in jobs.events(job_id) if not args.type or e.get("type") in args.type]
    for e in evs[-args.tail:] if args.tail else evs:
        text = e.get("msg") or (f"ok={e.get('ok')} exit_code={e.get('exit_code')}" + (
            f" error={e['error']}" if e.get("error") else "") if e.get("type") == "result" else "")
        out("job_event", f"[{e.get('type')}] {text}".rstrip(), event=e)
    return {"ok": True, "id": job_id, "shown": min(len(evs), args.tail or len(evs)), "total": len(evs)}


def cmd_jobs_stop(args, out):
    job_id = find_job(args)
    if jobs.snapshot(job_id)["state"] != "running":
        out("event", f"Job {job_id} is not running.")
        return job_result(jobs.snapshot(job_id))[1] | {"already_done": True}
    jobs.request_stop(job_id)
    if args.force:      # a second Ctrl+C: unmount even while setup still runs
        time.sleep(1.5)
        jobs.request_stop(job_id)
    deadline = time.time() + 20
    while jobs.snapshot(job_id)["state"] == "running" and time.time() < deadline:
        time.sleep(0.5)
    snap = jobs.snapshot(job_id)
    out("job", job_line(snap))
    if snap["state"] == "running":
        raise Stop(1, f"Job {job_id} is still running (setup may be holding it).",
                   fix=command_line(["jobs", "stop", job_id, "--force"]))
    return dict(snap, ok=True)


# ---------- scan ----------
RAR_PART = re.compile(r"^(?P<base>.+)\.part(?P<n>\d+)\.(?P<ext>rar|dat)$", re.I)
OLD_PART = re.compile(r"^(?P<base>.+)\.r(?P<n>\d\d)$", re.I)


def cmd_scan(args, out):
    root = os.path.abspath(args.folder)
    if not os.path.isdir(root):
        raise Stop(2, f"Folder not found: {root}")
    sets, isos, others = {}, [], {}
    base_depth = root.rstrip(os.sep).count(os.sep)
    for folder, dirs, names in os.walk(root):
        if folder.count(os.sep) - base_depth >= args.depth:
            dirs[:] = []
        for name in names:
            path = os.path.join(folder, name)
            m = RAR_PART.match(name)
            o = OLD_PART.match(name)
            if m and (m["ext"].lower() == "rar" or sz.has_rar_signature(path)):   # .dat: renamed RAR parts only
                sets.setdefault((folder, m["base"]), []).append((int(m["n"]), path))
            elif name.lower().endswith(".rar"):
                sets.setdefault((folder, name[:-4]), []).append((0, path))
            elif o:
                sets.setdefault((folder, o["base"]), []).append((int(o["n"]) + 1, path))
            elif name.lower().endswith(".iso"):
                isos.append(path)
            elif sz.classify(name):
                base, number, kind = sz.classify(name)
                # `x.zip` and its `x.z01 ...` pieces are one set; numbered volumes are one per base name
                group = "volume" if kind == "volume" else "single"
                stem = base + ".zip" if kind == "zsplit" else base
                others.setdefault((folder, stem.lower(), group), []).append((number, path))
    found_sets = []
    for (folder, base), parts in sorted(sets.items()):
        parts.sort()
        numbers = [n for n, _ in parts]
        first = parts[0][1]
        new_style = any(RAR_PART.match(os.path.basename(p)) for _, p in parts)
        expected = range(1, max(numbers) + 1) if new_style else range(0, max(numbers) + 1)
        missing = [n for n in expected if n not in numbers]
        # The highest part says more follow: the next ones aren't here (yet). Only the next
        # number is known; how many more there are is not.
        more = new_style and ex.rar_more_volumes(parts[-1][1]) is True
        if more:
            missing.append(max(numbers) + 1)
        busy = [n for n, p in parts if ex.in_use(p)]      # still being copied or downloaded
        size = sum(os.path.getsize(p) for _, p in parts)
        found_sets.append(first)
        out("rar_set", f"RAR set: {first} ({len(parts)} parts, {ex.human(size)})"
                       + (f" - MISSING parts {missing}" if missing else "")
                       + (f" - STILL BEING WRITTEN: parts {busy}" if busy else ""),
            first=first, parts=len(parts), size=size, missing=missing, busy=busy, more_after=more,
            next=command_line(["rar", "inspect", first]))
    found_archives = 0
    for (folder, _, group), parts in sorted(others.items()):
        parts.sort()
        numbers = [n for n, _ in parts]
        first = sz.first_volume(parts[0][1])
        numbered = group == "volume" or any(sz.ZIP_SPLIT.match(os.path.basename(p)) for _, p in parts)
        missing = [n for n in range(1, max(numbers) + 1) if n not in numbers] if numbered else []
        busy = [n for n, p in parts if ex.in_use(p)]
        size = sum(os.path.getsize(p) for _, p in parts)
        fmt = os.path.splitext(first)[1].lstrip(".").lower() or "archive"
        if group == "volume":
            fmt = os.path.splitext(os.path.splitext(first)[0])[1].lstrip(".").lower()
        found_archives += 1
        out("archive_set", f"Archive ({fmt}): {first} ({len(parts)} {'part' if len(parts) == 1 else 'parts'}, "
                           f"{ex.human(size)})" + (f" - MISSING parts {missing}" if missing else "")
                           + (" - STILL BEING WRITTEN" if busy else ""),
            first=first, format=fmt, parts=len(parts), size=size, missing=missing, busy=busy,
            next=command_line(["archive", "inspect", first]))
    for path in sorted(isos):
        size = os.path.getsize(path)
        freed = iso.was_freed(path)
        busy = ex.in_use(path)
        out("found_iso", f"ISO: {path} ({ex.human(size)})" + (" - already partly freed" if freed else "")
                         + (" - STILL BEING WRITTEN" if busy else ""),
            path=path, size=size, was_freed=freed, busy=busy, next=command_line(["iso", "inspect", path]))
    return {"ok": True, "folder": root, "rar_sets": len(found_sets), "archives": found_archives, "isos": len(isos)}


# ---------- schema ----------
def command_spec(parser, path):
    """Every leaf command under `parser`, with its arguments and examples."""
    out = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out += command_spec(sub, path + [name])
    if out or not path:
        return out
    examples = [line.strip() for line in (parser.epilog or "").splitlines() if line.strip().startswith(PROG)]
    return [{"command": " ".join(path), "help": parser.description,
             "args": [arg_spec(a) for a in parser._actions if arg_spec(a)["name"] not in GLOBAL_FLAGS
                      and not isinstance(a, (argparse._HelpAction, argparse._VersionAction))],
             "examples": examples}]


GLOBAL_FLAGS = ("--json", "--quiet", "--verbose", "--progress-every")


def arg_spec(a):
    """One argument, keeping only fields that say something."""
    spec = {"name": a.option_strings[-1] if a.option_strings else a.dest}
    if not a.option_strings:
        spec["positional"] = True
    if a.required or (not a.option_strings and a.nargs is None):
        spec["required"] = True
    if a.nargs != 0:
        spec["value"] = a.metavar or a.dest.upper()
    if isinstance(a, argparse._AppendAction):
        spec["repeatable"] = True
    if a.default not in (None, argparse.SUPPRESS, False, []):
        spec["default"] = a.default
    spec["help"] = a.help
    return spec


def cmd_schema(args, out):
    parser = build_parser()
    spec = {"program": PROG, "version": VERSION, "schema": SCHEMA,
            "exit_codes": {str(k): v for k, v in EXIT.items()},
            "global_flags": [arg_spec(a) for a in parser._actions if a.option_strings
                             and a.option_strings[-1] in GLOBAL_FLAGS],
            "commands": command_spec(parser, [])}
    if out.as_json:
        out("schema", None, **spec)
    else:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
    return {"ok": True, "commands": len(spec["commands"])}


# ---------- system ----------
def fusepy_available():
    return paths.FROZEN or importlib.util.find_spec("fuse") is not None


def system_report():
    tool = ex.rar_tool()
    seven = sz.tool()
    return {
        "unrar": {"ok": bool(tool), "source": tool[0] if tool else None, "path": tool[1] if tool else None},
        "sevenzip": {"ok": bool(seven), "source": seven[0] if seven else None, "path": seven[1] if seven else None},
        "winfsp": {"ok": iso.winfsp_installed()},
        "fusepy": {"ok": fusepy_available()},
        "admin": {"ok": iso.is_admin()},
    }


def cmd_system_check(args, out):
    report = system_report()
    for name, r in report.items():
        out("check", f"{name:8} {'OK' if r['ok'] else 'MISSING'}" + (f"  ({r['source']}: {r['path']})"
                                                                      if r.get("path") else ""),
            name=name, **r)
    hints = {
        "unrar": "Install WinRAR, or put UnRAR.exe on PATH (needed for RAR archives).",
        "sevenzip": "Install 7-Zip, or put 7z.exe on PATH (needed for zip, 7z, tar, gz and the other formats).",
        "winfsp": f"Install the driver (as administrator): {PROG} system install-winfsp",
        "fusepy": f"Install the Python package: {PROG} system install-fusepy",
        "admin": "Not administrator: iso install can't run setup.exe from here (setups elevate "
                 "themselves and can't see a drive mounted by a normal process).",
    }
    for name, r in report.items():
        if not r["ok"]:
            out("hint", hints[name], name=name)
    missing = [k for k, r in report.items() if not r["ok"] and k != "admin"]
    return {"ok": not missing, "missing": missing, **{k: r["ok"] for k, r in report.items()}}


def cmd_system_install_winfsp(args, out):
    if iso.winfsp_installed():
        out("event", "WinFsp is already installed.")
        return {"ok": True, "already_installed": True}
    if args.dry_run:
        out("plan", f"Would install WinFsp silently from {iso.WINFSP_MSI}.")
        return {"ok": True, "dry_run": True}
    if not iso.is_admin():
        raise Stop(5, "Installing WinFsp needs administrator rights.",
                   fix=f"Run from an administrator terminal: {command_line(args.argv)}")
    out("event", "Installing WinFsp (about 30 seconds)...")
    error = iso.install_winfsp()
    if error:
        raise Stop(5, f"WinFsp install failed: {error}", fix="Get it from https://winfsp.dev and install it.")
    out("event", "WinFsp installed.")
    return {"ok": True, "already_installed": False}


def cmd_system_install_fusepy(args, out):
    if fusepy_available():
        out("event", "fusepy is already installed.")
        return {"ok": True, "already_installed": True}
    pip = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "fusepy"]
    if args.dry_run:
        out("plan", f"Would run: {subprocess.list2cmdline(pip)}")
        return {"ok": True, "dry_run": True}
    out("event", f"Installing fusepy into {sys.executable}...")
    r = subprocess.run(pip, capture_output=True, text=True)
    if r.returncode != 0 and not iso.is_admin():
        # A Python installed for all users can't be written without admin; fall back to the user site.
        r = subprocess.run(pip[:-1] + ["--user", "fusepy"], capture_output=True, text=True)
    importlib.invalidate_caches()
    if r.returncode != 0 or not fusepy_available():
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["pip found no fusepy afterwards"]
        raise Stop(5, f"fusepy install failed: {tail[0]}",
                   fix=f"{subprocess.list2cmdline(pip[:3])} install fusepy")
    out("event", "fusepy installed.")
    return {"ok": True, "already_installed": False}


# ---------- rar ----------
def read_password(args):
    if getattr(args, "password_stdin", False):
        return sys.stdin.readline().rstrip("\r\n") or None
    return args.password or os.environ.get("EE_PASSWORD") or None


def archive_dest(args, first):
    if getattr(args, "dest", None):
        return os.path.abspath(args.dest)
    return (ex.default_dest if sz.is_rar(first) else sz.default_dest)(first)


def engine_errors(args):
    """Turns extractor errors into Stops with the right exit code and fix."""
    class Guard:
        def __enter__(self):
            return self

        def __exit__(self, kind, e, tb):
            if isinstance(e, ex.PasswordError):
                argv = [a for a in args.argv if a != args.archive]
                raise Stop(3, str(e), fix=f"echo <password> | {command_line(argv, args.archive, '--password-stdin')}")
            if isinstance(e, ex.ExtractError):
                if "UnRAR.exe not found" in str(e) or "7z.exe not found" in str(e):
                    raise Stop(5, str(e), fix=f"{PROG} system check")
                raise Stop(1, str(e))
            return False
    return Guard()


def load_archive(args):
    path = os.path.abspath(args.archive)
    if not os.path.isfile(path):
        raise Stop(2, f"Archive not found: {path}",
                   fix=f"Pass the first part of the set: {PROG} {args.group} {args.cmd} \"D:\\Games\\Game.part1.rar\"")
    with engine_errors(args):
        return ex.inspect(path, args.pw)


def load_set(args):
    """(info, journal). A `--delete` run that was stopped or crashed leaves a journal next to
    the parts; then the set is rebuilt from it and extraction continues at the first part left."""
    path = os.path.abspath(args.archive)
    journal = ex.read_journal(path)
    if journal and (getattr(args, "delete", False) or journal.get("deleted")):
        folder = os.path.dirname(path)
        volumes = [os.path.join(folder, n) for n in journal["parts"]]
        deleted = set(journal.get("deleted", []))
        left = [v for v in volumes if os.path.basename(v) not in deleted]
        missing = [os.path.basename(v) for v in left if not os.path.exists(v)]
        if missing:
            raise Stop(1, f"Cannot resume: {missing[0]} is missing. It was not extracted yet; put it back "
                          "next to the other parts.")
        sizes = journal.get("sizes") or []
        for v in left:
            i = volumes.index(v)
            if i < len(sizes) and os.path.getsize(v) != sizes[i]:
                raise Stop(1, f"Cannot resume: {os.path.basename(v)} changed since the extraction started.")
        info = ex.ArchiveInfo(volumes[0], volumes, journal.get("unpacked", 0), journal.get("files", 0),
                              args.pw, start=left[0] if left else volumes[-1])
        if left:
            with engine_errors(args):
                info.layout()
        return info, journal
    info = load_archive(args)
    if getattr(args, "delete", False):
        with engine_errors(args):
            info.layout()
    return info, None


def skipped(journal):
    """Files a resumed run leaves alone: those done, and those lost to a part deleted early."""
    if not journal:
        return set(), []
    done = set(journal.get("done", []))
    return done, sorted(set(journal.get("at_risk", [])) - done)


def space_plan(info, dest, delete, early=False, journal=None):
    done, lost = skipped(journal)
    free = ex.free_space(dest)
    if not delete:
        need = ex.space_needed(info, dest, False)
        return {"dest": dest, "needed": need, "free": free, "enough": free >= need, "mode": "keep"}
    skip = done | set(lost)
    safe = ex.space_needed(info, dest, True, ex.SAFE, skip)
    fast = ex.space_needed(info, dest, True, ex.EARLY, skip)
    need = fast if early else safe
    return {"dest": dest, "needed": need, "free": free, "enough": free >= need,
            "mode": ex.EARLY if early else ex.SAFE, "needed_safe": safe, "needed_early": fast,
            "early_fits": free >= fast, "solid": info.layout().solid}


def space_stop(args, space):
    dest, need, free = space["dest"], space["needed"], space["free"]
    if space["mode"] == ex.SAFE and space["early_fits"]:
        return Stop(4, f"Not enough free space to extract safely: needs {ex.human(need)}, {ex.human(free)} free. "
                       f"Deleting each part as soon as it is read needs only {ex.human(space['needed_early'])}, "
                       "but a stop or crash midway then loses the file being extracted.",
                    fix=command_line(args.argv, "--early-delete"), **space)
    return Stop(4, f"Not enough free space for {dest}: {ex.human(need - free)} short.",
                fix=f"Free some space, or try anyway: {command_line(args.argv, '--ignore-space')}", **space)


def space_text(space):
    text = f"Extract to {space['dest']}: free {ex.human(space['free'])}, needed {ex.human(space['needed'])}"
    if space["mode"] != "keep":
        text += f" ({space['mode']} delete)"
    return text + f" ({'OK' if space['enough'] else 'NOT ENOUGH'})"


def archive_event(out, info):
    parts = len(info.volumes)
    fmt = getattr(info, "kind", None)
    out("archive", f"{parts} {'part' if parts == 1 else 'parts'}, {info.files} files, {ex.human(info.packed)} "
                   f"packed -> {ex.human(info.unpacked)} unpacked", first=info.first, volumes=info.volumes,
        files=info.files, packed=info.packed, unpacked=info.unpacked, **({"format": fmt} if fmt else {}))


def cmd_rar_inspect(args, out):
    info, journal = load_set(args)
    dest = journal["dest"] if journal else archive_dest(args, info.first)
    space = space_plan(info, dest, args.delete or bool(journal), args.early_delete, journal)
    archive_event(out, info)
    out("space", space_text(space), **space)
    return {"ok": True, "parts": len(info.volumes), "unpacked": info.unpacked, "dest": dest,
            "space_ok": space["enough"], "resume": bool(journal),
            "next": command_line(["rar", "extract", info.first, "--dest", dest]
                                 + (["--delete"] if args.delete or journal else [])
                                 + (["--early-delete"] if args.early_delete else []) + ["--dry-run"])}


class Progress:
    """Turns Runner callbacks into a few progress events: one when a phase starts, then at
    most one every `every` seconds, then one at the end. Each carries the whole job's
    percent (weighted by part size), an ETA and how many files are done, so one event
    says where things stand."""

    def __init__(self, out, info, every):
        self.out = out
        self.every = every
        sizes = [os.path.getsize(v) if os.path.exists(v) else 0 for v in info.volumes]
        self.whole = getattr(info, "single_progress", False)    # 7-Zip reports one percentage for the whole set
        if self.whole:
            sizes = [sum(sizes) or 1]
        total = sum(sizes) or 1
        self.before = [sum(sizes[:i]) / total for i in range(len(sizes))]   # share done before part i
        self.share = [s / total for s in sizes]
        self.files = info.files
        self.phase = ""
        self.started = time.time()
        self.last_emit = 0
        self.state = (1, 0)
        self.files_done = 0

    def start(self, phase):
        self.phase, self.started, self.last_emit, self.files_done = phase, time.time(), 0, 0
        self.state = (1, 0)
        self.emit(force=True)

    def __call__(self, pct, part, total):
        part = min(part, total)
        self.state = (part, pct if pct is not None else (0 if part != self.state[0] else self.state[1]))
        self.emit()

    def file_done(self):
        self.files_done += 1

    def overall(self):
        part, pct = self.state
        i = part - 1
        return min(100.0, 100 * (self.before[i] + self.share[i] * pct / 100)) if i < len(self.share) else 100.0

    def emit(self, force=False, done=False):
        now = time.time()
        if not force and not done and now - self.last_emit < self.every:
            return
        self.last_emit = now
        overall = 100.0 if done else self.overall()
        elapsed = now - self.started
        eta = round(elapsed * (100 - overall) / overall) if 1 <= overall < 100 else None
        part, pct = self.state
        where = ([] if self.whole else [f"part {part} of {len(self.share)}"]) \
            + ([f"{self.files_done} of {self.files} files" if self.files else f"{self.files_done} files"]
               if self.files_done else [])
        text = (f"{self.phase}: {overall:.0f}%" + (f" ({', '.join(where)})" if where else "")
                + (f", about {eta} s left" if eta is not None else ""))
        self.out("progress", text, phase=self.phase.lower(), overall=round(overall, 1), part=part,
                 parts=len(self.share), part_percent=pct, files_done=self.files_done, files=self.files,
                 elapsed_s=round(elapsed, 1), eta_s=eta, **({"whole": True} if self.whole else {}))


# UnRAR lines worth showing without --verbose; the rest are one line per file.
# Per-part lines ("Extracting from ...") are left out too: progress events already say the part.
IMPORTANT_LINE = re.compile(r"^(Deleted|Could not|Verif|Extraction|Total errors)|error|corrupt|password|"
                            r"Cannot|No files", re.I)
FILE_LINE = re.compile(r"^(Extracting|Testing|\.\.\.)\s+.*\s(OK|\d{1,3}%)?\s*$")


def unrar_log(out, progress, verbose):
    """Log callback for the Runner: counts finished files, passes on what matters."""
    def log(text):
        if text.rstrip().endswith(" OK") and FILE_LINE.match(text):
            progress.file_done()
        if verbose or IMPORTANT_LINE.search(text) and not FILE_LINE.match(text):
            out("log", " ".join(text.split()))
    return log


def run_job(runner, job):
    try:
        job()
    except KeyboardInterrupt:
        runner.stop()
        raise Stop(130, "Stopped with Ctrl+C.")
    except ex.PasswordError as e:
        raise Stop(3, str(e))
    except ex.ExtractError as e:
        raise Stop(1, str(e))


def cmd_rar_verify(args, out):
    info = load_archive(args)
    if args.background:
        return start_background(args, out)
    progress = Progress(out, info, args.progress_every)
    runner = ex.Runner(log=unrar_log(out, progress, args.verbose), progress=progress, password=args.pw)

    def job():
        progress.start("Verifying")
        runner.verify(info)
        progress.emit(done=True)

    run_job(runner, job)
    return {"ok": True, "parts": len(info.volumes), "files": info.files,
            "next": command_line(["rar", "extract", info.first, "--dry-run"])}


def already_extracted(args):
    """An earlier `rar extract --delete` finished and removed the archive: report it as done
    instead of failing, so a retried command is safe."""
    first = os.path.abspath(args.archive)
    if os.path.exists(first):
        return None
    return already_extracted_at(first, archive_dest(args, first))


def already_extracted_at(first, dest):
    """The done-marker in `dest` if it says `first`'s archive was extracted and deleted there."""
    try:
        with open(os.path.join(dest, DONE_MARKER), encoding="utf-8") as f:
            done = json.load(f)
    except (OSError, ValueError):
        return None
    return done if os.path.normcase(done.get("archive", "")) == os.path.normcase(os.path.basename(first)) else None


def cmd_rar_extract(args, out):
    info, journal = load_set(args) if ex.read_journal(args.archive) else (None, None)
    if not journal:
        done = already_extracted(args)
        if done:
            dest = archive_dest(args, os.path.abspath(args.archive))
            out("event", f"Already extracted to {dest} (the parts were deleted then).")
            return {"ok": True, "already_done": True, "dest": dest,
                    **{k: done[k] for k in ("files", "unpacked") if k in done}}
        info, journal = load_set(args)
    delete = args.delete or bool(journal)
    done, lost = skipped(journal)
    if journal:
        dest = journal["dest"]
        if args.dest and os.path.normcase(os.path.abspath(args.dest)) != os.path.normcase(dest):
            out("event", f"Resuming into {dest}, where this extraction started.")
        out("event", f"Resuming: {len(done)} of {info.files} files are already extracted.")
        if lost:
            out("warning", f"{len(lost)} file(s) cannot be recovered: their start was in a part deleted "
                           f"early. First: {lost[0]}")
    else:
        dest = archive_dest(args, info.first)
    if args.early_delete and not delete:
        raise Stop(2, "--early-delete only applies with --delete.", fix=command_line(args.argv, "--delete"))
    space = space_plan(info, dest, delete, args.early_delete, journal)
    out("space", space_text(space), **space)
    if not space["enough"] and not args.ignore_space:
        raise space_stop(args, space)
    remaining = [v for v in info.volumes if os.path.exists(v)]
    mode = space["mode"]
    if args.dry_run:
        archive_event(out, info)
        steps = ([f"skip the {len(done)} files already extracted"] if journal else []) \
            + ([] if args.no_verify else ["verify the parts left" if journal else "verify every part"]) \
            + [f"extract to {dest}"]
        if mode == ex.SAFE:
            steps.append(f"delete each of the {len(remaining)} parts once every file in it is extracted")
        elif mode == ex.EARLY:
            steps.append(f"delete each of the {len(remaining)} parts as soon as it is read")
        out("plan", "Would " + ", then ".join(steps) + ".", steps=steps, mode=mode,
            deletes=remaining if delete else [], resume=bool(journal), lost=lost, done=len(done), files=info.files)
        real = [a for a in args.argv if a != "--dry-run"] + ["--background"]
        return {"ok": True, "dry_run": True, "dest": dest, "needs_yes": delete, "mode": mode,
                "resume": bool(journal), "next": command_line(real, *(["--yes"] if delete else []))}
    if delete and not args.yes:
        raise Stop(6, ("--delete --early-delete removes each part as soon as it is read; if extraction stops "
                       "midway, the file being extracted is lost." if mode == ex.EARLY else
                       "--delete removes each part once every file in it is extracted; a stopped run can "
                       "be resumed by running the same command again."), fix=with_yes(args))
    if delete and args.no_verify:
        out("warning", "Verification is off: a corrupt part would only be found after earlier parts "
                       "were deleted.")
    if args.background:
        return start_background(args, out)
    progress = Progress(out, info, args.progress_every)
    runner = ex.Runner(log=unrar_log(out, progress, args.verbose), progress=progress, password=args.pw)
    result = {}

    def job():
        if not args.no_verify:
            progress.start("Verifying")
            runner.verify(info, sorted(done | set(lost)))
            progress.emit(done=True)
        progress.start("Extracting")
        result["freer"] = runner.extract(info, dest, delete, mode if delete else ex.SAFE, journal)
        progress.emit(done=True)

    try:
        if remaining:
            run_job(runner, job)
        elif delete:                    # stopped after the last part went: only the wrap-up was left
            result["freer"] = ex.PartFreer(info, dest, mode, lambda t: out("log", t), journal)
            result["freer"].finish()
    except Stop as e:
        resumable = delete and os.path.exists(ex.journal_path(info.first))
        e.extra.update(parts_left=len(ex.remaining_parts(info)), parts=len(info.volumes), resumable=resumable)
        if resumable:
            e.fix = command_line([a for a in args.argv if a != "--background"])
        raise
    freer = result.get("freer")
    lost = freer.lost if freer else []
    if delete:
        with open(os.path.join(dest, DONE_MARKER), "w", encoding="utf-8") as f:
            json.dump({"archive": os.path.basename(info.first), "files": info.files,
                       "unpacked": info.unpacked}, f)
    return {"ok": True, "dest": dest, "files": info.files, "unpacked": info.unpacked, "mode": mode,
            "parts": len(info.volumes), "parts_left": len(ex.remaining_parts(info)), "lost": lost}


# ---------- everything but RAR: zip, 7z, tar, gz, ... through 7-Zip ----------
# Same commands and result fields as the RAR ones, so a caller does not care which engine ran.
# The one difference is --delete: 7-Zip cannot free pieces while it reads, so the whole archive
# is removed once a verified extraction finished without a single error.
def load_generic(args):
    path = os.path.abspath(args.archive)
    if not os.path.isfile(sz.first_volume(path)):
        raise Stop(2, f"Archive not found: {path}",
                   fix=f"Pass the archive itself: {PROG} {args.group} {args.cmd} \"D:\\Downloads\\Pack.zip\"")
    with engine_errors(args):
        return sz.inspect(path, args.pw)


def generic_space(info, dest, delete):
    free = ex.free_space(dest)
    need = sz.space_needed(info, dest)
    return {"dest": dest, "needed": need, "free": free, "enough": free >= need,
            "mode": "after" if delete else "keep", "generic": True}


def generic_space_text(space):
    return (f"Extract to {space['dest']}: free {ex.human(space['free'])}, needed {ex.human(space['needed'])}"
            + (" (archive deleted afterwards)" if space["mode"] == "after" else "")
            + f" ({'OK' if space['enough'] else 'NOT ENOUGH'})")


def reject_rar_only(args):
    if getattr(args, "early_delete", False):
        raise Stop(2, "--early-delete only applies to RAR sets: other formats cannot be freed while they are read.",
                   fix=command_line([a for a in args.argv if a != "--early-delete"]))


def generic_inspect(args, out):
    reject_rar_only(args)
    info = load_generic(args)
    dest = archive_dest(args, info.first)
    space = generic_space(info, dest, args.delete)
    archive_event(out, info)
    out("space", generic_space_text(space), **space)
    return {"ok": True, "parts": len(info.volumes), "unpacked": info.unpacked, "dest": dest,
            "space_ok": space["enough"], "resume": False, "format": info.kind,
            "next": command_line(["archive", "extract", info.first, "--dest", dest]
                                 + (["--delete"] if args.delete else []) + ["--dry-run"])}


SZ_FILE = re.compile(r"^[-T] (?P<name>.+)$")
SZ_IMPORTANT = re.compile(r"^(Deleted|Could not|Verif|Extraction)|ERROR|Wrong password|CRC|Data Error|Warning|"
                          r"Unexpected end|Can't open|Cannot|Everything is Ok", re.I)


def seven_log(out, progress, verbose):
    """Log callback for the 7-Zip runner: counts finished files, passes on what matters."""
    def log(text):
        m = SZ_FILE.match(text)
        if m:
            if not m["name"].endswith("\\"):        # a folder line, not a file
                progress.file_done()
            if verbose:
                out("log", text)
        elif verbose or SZ_IMPORTANT.search(text):
            out("log", " ".join(text.split()))
    return log


def generic_verify(args, out):
    info = load_generic(args)
    if args.background:
        return start_background(args, out)
    progress = Progress(out, info, args.progress_every)
    runner = sz.Runner(log=seven_log(out, progress, args.verbose), progress=progress, password=args.pw)

    def job():
        progress.start("Verifying")
        runner.verify(info)
        progress.emit(done=True)

    run_job(runner, job)
    return {"ok": True, "parts": len(info.volumes), "files": info.files,
            "next": command_line(["archive", "extract", info.first, "--dry-run"])}


def generic_extract(args, out):
    reject_rar_only(args)
    first = sz.first_volume(args.archive)
    if not os.path.exists(first):
        done = already_extracted_at(first, archive_dest(args, first))
        if done:
            dest = archive_dest(args, first)
            out("event", f"Already extracted to {dest} (the archive was deleted then).")
            return {"ok": True, "already_done": True, "dest": dest,
                    **{k: done[k] for k in ("files", "unpacked") if k in done}}
    info = load_generic(args)
    dest = archive_dest(args, info.first)
    delete = args.delete
    space = generic_space(info, dest, delete)
    out("space", generic_space_text(space), **space)
    if not space["enough"] and not args.ignore_space:
        raise Stop(4, f"Not enough free space for {dest}: {ex.human(space['needed'] - space['free'])} short.",
                   fix=f"Free some space, or try anyway: {command_line(args.argv, '--ignore-space')}", **space)
    if args.dry_run:
        archive_event(out, info)
        steps = ([] if args.no_verify else ["verify the archive"]) + [f"extract to {dest}"]
        if delete:
            steps.append(f"delete the archive ({len(info.volumes)} {'file' if len(info.volumes) == 1 else 'files'}) "
                         "once the extraction finished without errors")
        out("plan", "Would " + ", then ".join(steps) + ".", steps=steps, mode=space["mode"],
            deletes=info.volumes if delete else [], resume=False, lost=[], done=0, files=info.files)
        real = [a for a in args.argv if a != "--dry-run"] + ["--background"]
        return {"ok": True, "dry_run": True, "dest": dest, "needs_yes": delete, "mode": space["mode"],
                "resume": False, "next": command_line(real, *(["--yes"] if delete else []))}
    if delete and not args.yes:
        raise Stop(6, f"--delete removes {os.path.basename(info.first)}"
                      + (f" and its {len(info.volumes) - 1} other parts" if len(info.volumes) > 1 else "")
                      + " once the extraction finished without errors.", fix=with_yes(args))
    if args.background:
        return start_background(args, out)
    progress = Progress(out, info, args.progress_every)
    runner = sz.Runner(log=seven_log(out, progress, args.verbose), progress=progress, password=args.pw)
    freed = {}

    def job():
        if not args.no_verify:
            progress.start("Verifying")
            runner.verify(info)
            progress.emit(done=True)
        progress.start("Extracting")
        runner.extract(info, dest, delete)
        progress.emit(done=True)
        if delete:
            freed["bytes"] = sz.delete_volumes(info, lambda t: out("log", t))

    run_job(runner, job)
    if delete:
        with open(os.path.join(dest, DONE_MARKER), "w", encoding="utf-8") as f:
            json.dump({"archive": os.path.basename(info.first), "files": info.files, "unpacked": info.unpacked}, f)
    left = [v for v in info.volumes if os.path.exists(v)]
    return {"ok": True, "dest": dest, "files": info.files, "unpacked": info.unpacked, "mode": space["mode"],
            "parts": len(info.volumes), "parts_left": len(left), "lost": [], "format": info.kind,
            **({"freed": freed["bytes"]} if delete else {})}


# One entry point per command for both groups (`rar` and `archive`): RAR sets go to UnRAR, the rest to 7-Zip.
def cmd_archive_inspect(args, out):
    return (cmd_rar_inspect if sz.is_rar(args.archive) else generic_inspect)(args, out)


def cmd_archive_verify(args, out):
    return (cmd_rar_verify if sz.is_rar(args.archive) else generic_verify)(args, out)


def cmd_archive_extract(args, out):
    return (cmd_rar_extract if sz.is_rar(args.archive) else generic_extract)(args, out)


# ---------- iso ----------
def load_iso(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise Stop(2, f"ISO not found: {path}")
    try:
        ex.check_not_busy([path])
    except ex.ExtractError as e:
        raise Stop(2, str(e))
    try:
        img = udf.UDFImage(path)
    except (OSError, udf.UDFError) as e:
        raise Stop(2, f"Cannot read this ISO: {e}")
    img.close()
    return path, img.files()


def install_size(args):
    return int(args.install_size_mb * iso.MB) if args.install_size_mb else None


def cmd_iso_status(args, out):
    """Lightweight status check used while the ISO setup screen is open."""
    path = os.path.abspath(args.iso)
    exists = os.path.isfile(path)
    attached = iso.iso_attached(path) if exists else False
    message = ("ISO is mounted by Windows" if attached else
               "ISO file is unavailable" if not exists else
               "Windows has not mounted this ISO")
    out("check", message, name="iso_mount", path=path, exists=exists,
        windows_mounted=attached)
    return {"ok": True, "path": path, "exists": exists,
            "windows_mounted": attached}


def cmd_iso_inspect(args, out):
    path, files = load_iso(args.iso)
    total = sum(e.size for e in files)
    has_setup = any(e.path.lower() == "/setup.exe" for e in files)
    big = [e for e in files if e.path.lower().endswith(".bin") and e.size >= 256 * iso.MB]
    out("iso", f"{os.path.basename(path)}: {len(files)} files, {iso.human(total)}; setup.exe in root: "
               f"{'yes' if has_setup else 'NO'}; {len(big)} big .bin files can be freed",
        path=path, files=len(files), size=total, has_setup=has_setup, freeable=[e.path for e in big])
    if args.files:
        for e in files:
            out("file", f"{e.size:>16,}  {e.path}", path=e.path, size=e.size)
    freed = iso.was_freed(path)
    if freed:
        out("warning", "This ISO was already partly freed in an earlier run; freed parts are gone.")
    attached = iso.iso_attached(path)
    if attached:
        out("warning", "Windows has this ISO mounted; eject it before iso install.")
    result = {"ok": True, "files": len(files), "size": total, "has_setup": has_setup,
              "was_freed": freed, "windows_mounted": attached}
    size = install_size(args)
    if size:
        need, growth = iso.space_needed(args.buffer_gb, size, files)
        free = iso.drive_free(path)
        out("space", f"Free {iso.human(free)}, needed {iso.human(need)} ({args.buffer_gb:g} GB buffer + "
                     f"{iso.EXTRA_NEEDED_GB} GB margin + {iso.human(growth)} game bigger than ISO): "
                     f"{'OK' if free >= need else 'NOT ENOUGH'}", free=free, needed=need, growth=growth,
            enough=free >= need)
        result["space_ok"] = free >= need
    result["next"] = command_line(["iso", "install", path, "--install-dir", "<folder>", "--install-size-mb",
                                   f"{args.install_size_mb:g}" if size else "<MB from setup>", "--silent",
                                   "--dry-run"])
    return result


def wait_for_drive(drive, out, timeout=30):
    """Wait until the drive process says it mounted and the letter shows up."""
    deadline = time.time() + timeout
    mounted = False
    while time.time() < deadline:
        for msg in drive.poll(timeout=0.25):
            t = msg.get("type")
            if t == "mounted":
                mounted = True
            elif t == "fatal":
                raise Stop(1, msg["msg"])
            elif t == "ended":
                raise Stop(1, f"The virtual drive stopped before mounting (exit code {msg['code']}).")
            elif t == "event":
                out("event", msg["msg"])
        if mounted and os.path.exists(drive.letter + "\\"):
            return
    raise Stop(1, f"Drive {drive.letter} did not appear within {timeout} seconds.")


STATUS_HEARTBEAT = 60      # an unchanged status is still repeated this often, so a reader sees it's alive


def report_drive(drive, out, msgs, status_every, last):
    """Pass drive messages on, and a status line when it changed (at most every
    `status_every` s) or once a minute as a heartbeat. `last` is {"t": time, "key": ...}
    from the previous call. Returns (ended, last)."""
    ended = False
    for msg in msgs:
        t = msg.get("type")
        if t == "event":
            bad = msg["msg"].startswith(("BLOCKED", "Freeing STOPPED", "Freeing error"))
            out("warning" if bad else "event", msg["msg"])
        elif t == "fatal":
            out("error", msg["msg"])
        elif t == "ended":
            ended = True
    st = drive.status
    since = time.time() - last["t"]
    if not st or since < status_every:
        return ended, last
    files = st["files"].values()
    freed = sum(f["freed"] for f in files)
    # How far setup is through the ISO's data: a fair stand-in for install progress.
    total = sum(f["size"] for f in files) or 1
    overall = round(100 * sum(min(f["hwm"], f["size"]) for f in files) / total, 1)
    key = (overall, st["bytes_read"], freed, st["installed"], st["paused"], st["violations"])
    if key == last["key"] and since < STATUS_HEARTBEAT and status_every:
        return ended, last
    # The big files, for a per-file view (read position, freed bytes); small files are left out.
    bins = [{"path": p, "size": f["size"], "read": min(f["hwm"], f["size"]), "freed": f["freed"]}
            for p, f in sorted(st["files"].items()) if f["size"] >= 256 * iso.MB]
    out("status", f"{overall:.0f}% of the ISO read by setup: read {iso.human(st['bytes_read'])}, freed "
                  f"{iso.human(freed)}, installed {iso.human(st['installed'])}"
                  + (", FREEING STOPPED" if st["paused"] else ""),
        overall=overall, bytes_read=st["bytes_read"], freed=freed, installed=st["installed"],
        paused=st["paused"], violations=st["violations"], max_back=st["max_back"], bins=bins)
    return ended, {"t": time.time(), "key": key}


def unmount(drive, out, timeout=15):
    drive.quit()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(m.get("type") == "ended" for m in drive.poll(timeout=0.25)):
            out("event", f"Virtual drive {drive.letter} unmounted.")
            return
    drive.kill()
    out("warning", f"Virtual drive {drive.letter} did not unmount in time and was killed.")


def iso_preflight(args, out, path, files):
    """Every check before mounting; the same checks run for --dry-run. Raises Stop for
    anything that blocks the install."""
    freeing = not args.no_free
    run_setup = not args.no_setup
    if not iso.winfsp_installed():
        raise Stop(5, "WinFsp is not installed.", fix=f"{PROG} system install-winfsp   (as administrator)")
    if not fusepy_available():
        raise Stop(5, "fusepy is not installed.", fix=f"{PROG} system install-fusepy")
    if run_setup and not any(e.path.lower() == "/setup.exe" for e in files):
        raise Stop(2, "No setup.exe in the ISO root.", fix=command_line(args.argv, "--no-setup"))
    if run_setup and not iso.is_admin():
        raise Stop(5, "Not running as administrator. Game setups restart themselves as admin and then "
                      "can't see a drive mounted by a normal process.",
                   fix=f"Run from an administrator terminal: {command_line(args.argv)}")
    if not iso.is_admin():
        out("warning", "Not administrator: admin programs (like most setups) won't see the drive.")
    if args.buffer_gb < iso.MIN_BUFFER_GB:
        raise Stop(2, f"--buffer-gb must be at least {iso.MIN_BUFFER_GB}.")
    size = install_size(args)
    if freeing:
        example = (f"{PROG} iso install \"{path}\" --install-dir \"D:\\Games\\MyGame\" "
                   "--install-size-mb 52000 --yes")
        if not args.install_dir:
            raise Stop(2, "--install-dir is required: the folder setup installs into.", fix=example)
        if not size:
            raise Stop(2, "--install-size-mb is required: the number from setup's 'At least ... MB of "
                          "free disk space is required'.", fix=example)
        need, growth = iso.space_needed(args.buffer_gb, size, files)
        free = iso.drive_free(path)
        if free < need:
            raise Stop(4, f"Not enough free space: free {iso.human(free)}, needed {iso.human(need)} "
                          f"(= {args.buffer_gb:g} GB buffer + {iso.EXTRA_NEEDED_GB} GB margin + "
                          f"{iso.human(growth)} game bigger than ISO).",
                       fix="Free some space, lower --buffer-gb, or install without freeing: "
                           + command_line(args.argv, "--no-free"), free=free, needed=need)
        if os.path.splitdrive(os.path.abspath(args.install_dir))[0].lower() != os.path.splitdrive(path)[0].lower():
            out("warning", "The install folder is on a different drive than the ISO: freeing the ISO will "
                           "not make room on the install drive.")
        if iso.was_freed(path):
            out("warning", "This ISO was already partly freed in an earlier run; freed parts are gone.")
    if iso.iso_attached(path):
        raise Stop(1, "Windows has this ISO mounted.", fix="In Explorer, right-click its drive -> Eject.")
    if args.dry_run:
        return
    if freeing and not args.yes:
        raise Stop(6, f"Install while freeing deletes parts of the ISO as setup reads them (keeping the "
                      f"last {args.buffer_gb:g} GB). If setup fails, is cancelled or the PC crashes, the "
                      "ISO is lost. Use --no-free to change nothing.", fix=with_yes(args))
    if args.delete_iso and not args.yes:
        raise Stop(6, "--delete-iso deletes the ISO after a successful install.", fix=with_yes(args))


def cmd_iso_install(args, out):
    path, files = load_iso(args.iso)
    iso_preflight(args, out, path, files)
    mode = "dry" if args.no_free else "free"
    install_dir = os.path.abspath(args.install_dir) if args.install_dir else None
    if args.dry_run:
        steps = ["mount the ISO as a virtual drive" + ("" if args.no_free else " and free it behind setup")]
        if not args.no_setup:
            steps.append("run setup.exe" + (" silently into " + install_dir if args.silent and install_dir else ""))
            steps.append("check setup's exit code and log, then unmount")
            if args.delete_iso:
                steps.append("delete the ISO if setup fully succeeded")
        else:
            steps.append("serve the drive until 'quit' on stdin or Ctrl+C")
        out("plan", "Would " + ", then ".join(steps) + ".", steps=steps, mode=mode)
        needs_yes = not args.no_free or args.delete_iso
        real = [a for a in args.argv if a != "--dry-run"] + ["--background"]
        return {"ok": True, "dry_run": True, "mode": mode, "needs_yes": needs_yes,
                "next": command_line(real, *(["--yes"] if needs_yes and "--yes" not in real else []))}
    if args.background:
        return start_background(args, out)
    if install_dir:
        os.makedirs(install_dir, exist_ok=True)
    letter = iso.free_drive_letter()
    if not letter:
        raise Stop(1, "No free drive letter.")
    os.makedirs(iso.LOG_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    read_log = os.path.join(iso.LOG_DIR, f"{os.path.basename(path)}-{'dry-' if args.no_free else ''}{stamp}.csv")
    out("event", f"Mounting {os.path.basename(path)} as {letter} ({mode} mode, {args.buffer_gb:g} GB buffer)...",
        letter=letter, mode=mode, read_log=read_log)
    drive = iso.VDrive(path, letter, mode, args.buffer_gb, install_dir=install_dir, log=read_log)
    try:
        wait_for_drive(drive, out)
        out("mounted", f"Mounted as {letter}", letter=letter)
        if args.no_setup:
            return serve_until_quit(drive, out, args)
        return run_setup(drive, out, args, path, install_dir, stamp)
    finally:
        if drive.running():
            unmount(drive, out)


def serve_until_quit(drive, out, args):
    out("event", "Serving the drive. Send 'quit' on stdin (or press Ctrl+C) to unmount.")
    quit_typed = threading.Event()

    def watch_stdin():
        for line in sys.stdin:
            if line.strip() == "quit":
                quit_typed.set()
                return

    threading.Thread(target=watch_stdin, daemon=True).start()
    last = {"t": 0, "key": None}
    try:
        while not quit_typed.is_set():
            ended, last = report_drive(drive, out, drive.poll(timeout=0.5), args.status_every, last)
            if ended:
                raise Stop(1, "The virtual drive stopped unexpectedly.")
    except KeyboardInterrupt:
        pass
    unmount(drive, out)
    return {"ok": True, "letter": drive.letter}


def run_setup(drive, out, args, path, install_dir, stamp):
    exe = os.path.join(drive.letter + "\\", "setup.exe")
    setup_log = os.path.join(iso.LOG_DIR, f"setup-{stamp}.log")
    cmd = [exe, f"/LOG={setup_log}"]
    if args.silent:
        cmd += SETUP_SILENT + ([f"/DIR={install_dir}"] if install_dir else [])
    cmd += args.setup_arg
    try:
        setup = subprocess.Popen(cmd, cwd=drive.letter + "\\")
    except OSError as e:
        raise Stop(1, f"Could not start setup: {e}")
    out("setup_started", f"Started setup.exe{' (silent)' if args.silent else ''}; setup log: {setup_log}",
        command=cmd, setup_log=setup_log)
    if not args.silent:
        out("event", f"Choose this install folder in setup: {install_dir}")
    last = {"t": 0, "key": None}
    interrupted = False
    while True:
        try:
            ended, last = report_drive(drive, out, drive.poll(timeout=1), args.status_every, last)
            if ended:
                raise Stop(1, "The virtual drive stopped while setup was running.")
            code = setup.poll()
            if code is not None:
                break
        except KeyboardInterrupt:
            if interrupted:
                raise Stop(130, "Stopped with Ctrl+C while setup was still running.")
            interrupted = True
            out("warning", "Setup is still running and reads from the drive. Press Ctrl+C again to "
                           "unmount anyway (setup will fail; when freeing, the ISO is lost).")
    report_drive(drive, out, drive.poll(timeout=1.5), 0, {"t": 0, "key": None})    # pick up the final status
    st = drive.status or {"files": {}, "violations": 0, "paused": False}
    problems, unread = iso.setup_result(code, setup_log, st["files"])
    unmount(drive, out)
    result = {"setup_exit_code": code, "setup_log": setup_log, "problems": problems,
              "unread": unread, "violations": st["violations"], "freeing_stopped": st["paused"]}
    if problems:
        raise Stop(1, "Setup may not have finished: " + "; ".join(problems) + ". The ISO was kept.",
                   fix=f"Read the setup log: {setup_log}", **result)
    if unread:
        out("warning", "Setup finished but did not read to the end of: " + ", ".join(unread) +
                       " (normal for optional extras like languages). The ISO was kept.")
    else:
        out("event", "Setup finished successfully (exit code 0, log confirms, all .bin files read).")
        if args.delete_iso:
            result["iso_deleted_bytes"] = delete_iso(path, out)
    return dict(result, ok=True)


def delete_iso(path, out):
    try:
        on_disk = iso.delete_iso(path)
    except OSError as e:
        raise Stop(1, f"Could not delete the ISO: {e}")
    out("event", f"Deleted {path} ({iso.human(on_disk)} given back to the drive).", freed=on_disk)
    return on_disk


def cmd_iso_delete(args, out):
    path = os.path.abspath(args.iso)
    if not os.path.isfile(path):
        out("event", f"Already gone: {path}")
        return {"ok": True, "already_done": True, "path": path}
    if args.dry_run:
        out("plan", f"Would delete {path} and its freeing record.", path=path)
        return {"ok": True, "dry_run": True, "path": path, "size": os.path.getsize(path)}
    if not args.yes:
        raise Stop(6, f"This deletes {path} permanently.", fix=with_yes(args))
    return {"ok": True, "path": path, "freed": delete_iso(path, out)}


# ---------- arguments ----------
class Parser(argparse.ArgumentParser):
    """argparse that reports bad arguments in the requested format (JSON or text), and
    takes only full flag names, so a command means the same thing in every version."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        sample = next((line.strip() for line in (self.epilog or "").splitlines()
                       if line.strip().startswith(PROG)), None)
        raise Stop(2, message, fix=f"{sample}   (more: {self.prog} --help)" if sample else f"{self.prog} --help")


def examples(*lines):
    return "Examples:\n" + "\n".join(f"  {PROG} {line}" for line in lines)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="one JSON object per line on stdout (or set EE_JSON=1)")
    common.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="text mode: only data, warnings and errors")
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="also log every file UnRAR handles (normally only counted)")
    common.add_argument("--progress-every", type=float, default=argparse.SUPPRESS, metavar="S",
                        help="seconds between progress lines (default 2; 0 = every change)")
    fmt = argparse.RawDescriptionHelpFormatter
    background_help = "start detached and return a job id at once; follow it with `jobs wait`"

    def add(sub, name, func, text, epilog):
        p = sub.add_parser(name, parents=[common], help=text, description=text, epilog=epilog,
                           formatter_class=fmt)
        p.set_defaults(func=func)
        return p

    def group(name, text):
        g = sub.add_parser(name, parents=[common], help=text, description=text, formatter_class=fmt)
        g.set_defaults(func=None, parser=g)
        return g.add_subparsers(dest="cmd", metavar="<command>")

    ap = Parser(prog=PROG, parents=[common], formatter_class=fmt,
                description="EnhancedExtract in the terminal: extract RAR, zip, 7z, tar and other archives, and "
                            "install games from ISOs while freeing space as you go. Never prompts; everything "
                            "is a flag.",
                epilog="Typical agent flow:\n" + "\n".join(f"  {PROG} {line}" for line in (
                    "--json scan D:\\Downloads                       # find archives and ISOs",
                    "--json archive inspect D:\\Downloads\\Game.part1.rar  # sizes, space, next command",
                    "--json archive extract D:\\Downloads\\Game.part1.rar --delete --dry-run",
                    "--json archive extract D:\\Downloads\\Game.part1.rar --delete --yes --background",
                    "--json jobs wait --timeout 60                   # repeat until state is done",
                    "--json schema                                   # every command and flag, as JSON"))
                + "\n\n" + examples("system check", "rar extract Game.part1.rar --dry-run",
                                    "--json iso inspect Game.iso --install-size-mb 52000")
                + "\n\nExit codes:\n" + "\n".join(f"  {k:<4} {v}" for k, v in EXIT.items()))
    ap.add_argument("--version", action="version", version=f"EnhancedExtract CLI {VERSION}")
    ap.set_defaults(func=None, parser=ap)
    sub = ap.add_subparsers(dest="group", metavar="<group>")

    system = group("system", "what this PC has, and installing what's missing")
    add(system, "check", cmd_system_check, "report UnRAR, 7-Zip, WinFsp, fusepy and admin rights",
        examples("system check", "--json system check"))
    p = add(system, "install-winfsp", cmd_system_install_winfsp,
            "install the bundled WinFsp driver (needs admin; no-op if installed)",
            examples("system install-winfsp", "system install-winfsp --dry-run"))
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    p = add(system, "install-fusepy", cmd_system_install_fusepy,
            "pip-install fusepy into the Python running this (no-op if installed)",
            examples("system install-fusepy", "system install-fusepy --dry-run"))
    p.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")

    p = add(sub, "scan", cmd_scan, "find RAR sets, other archives (zip, 7z, tar ...) and ISOs in a folder; reads no archive",
            examples("scan D:\\Downloads", "--json scan D:\\Downloads --depth 3"))
    p.add_argument("folder", help="folder to look in")
    p.add_argument("--depth", type=int, default=2, help="how many folder levels down to look (default 2)")

    add(sub, "schema", cmd_schema, "every command, flag, example and exit code as one JSON document",
        examples("--json schema", "schema"))

    jobs_group = group("jobs", "follow commands started with --background")
    p = add(jobs_group, "list", cmd_jobs_list, "recent jobs, newest first", examples("jobs list", "--json jobs list"))
    p.add_argument("--limit", type=int, default=10, help="how many (default 10)")
    for name, func, text, ex_lines in (
            ("status", cmd_jobs_status, "where a job stands now (exit code 7 while running)",
             ["jobs status", "jobs status 20261105-221500-ab12"]),
            ("wait", cmd_jobs_wait, "wait until the job ends or --timeout passes (exit code 7 = still running)",
             ["jobs wait --timeout 60", "jobs wait ab12 --timeout 300"]),
            ("logs", cmd_jobs_logs, "the job's events (last 20 by default)",
             ["jobs logs", "jobs logs ab12 --type warning error", "jobs logs ab12 --tail 0"]),
            ("stop", cmd_jobs_stop, "stop a job cleanly, like Ctrl+C (kills UnRAR / unmounts the drive)",
             ["jobs stop ab12", "jobs stop ab12 --force"])):
        p = add(jobs_group, name, func, text, examples(*ex_lines))
        p.add_argument("id", nargs="?", help="job id, or a unique part of it (default: newest job)")
        if name == "wait":
            p.add_argument("--timeout", type=float, default=60, help="seconds to wait at most (default 60)")
        if name == "logs":
            p.add_argument("--tail", type=int, default=20, help="last N events (0 = all; default 20)")
            p.add_argument("--type", nargs="+", help="only these event types, e.g. warning error progress")
        if name == "stop":
            p.add_argument("--force", action="store_true",
                           help="stop even while setup is still running (setup fails; when freeing, the ISO is lost)")

    # `archive` takes any supported format and `rar` stays for existing scripts; both run the same
    # handlers, which send RAR sets to UnRAR and everything else (zip, 7z, tar, gz, ...) to 7-Zip.
    for grp, label, first_help, ex_lines in (
            ("archive", "any archive: RAR sets (UnRAR) and zip, 7z, tar, gz, bz2, xz, zst, cab, wim ... (7-Zip)",
             "the archive, or the first part of a set (Game.part1.rar, Pack.7z.001, Pack.zip)",
             {"inspect": ["archive inspect \"D:\\Downloads\\Pack.zip\"",
                          "archive inspect Game.part1.rar --dest \"D:\\Games\\Game\" --delete"],
              "verify": ["archive verify Pack.7z", "echo secret | archive verify Pack.zip --password-stdin"],
              "extract": ["archive extract Pack.zip --dest \"D:\\Games\\Pack\"",
                          "archive extract Pack.7z.001 --delete --dry-run",
                          "archive extract Pack.tar.gz --delete --yes",
                          "--json archive extract Pack.zip --yes --password-stdin < pw.txt"]}),
            ("rar", "multi-part RAR sets (the same commands as `archive`, which also takes other formats)",
             "first part of the set, e.g. Game.part1.rar",
             {"inspect": ["rar inspect \"D:\\Downloads\\Game.part1.rar\"",
                          "rar inspect Game.part1.rar --dest \"D:\\Games\\Game\" --delete"],
              "verify": ["rar verify Game.part1.rar", "echo secret | rar verify Game.part1.rar --password-stdin"],
              "extract": ["rar extract Game.part1.rar --dest \"D:\\Games\\Game\"",
                          "rar extract Game.part1.rar --delete --dry-run",
                          "rar extract Game.part1.rar --delete --yes",
                          "--json rar extract Game.part1.rar --delete --yes --password-stdin < pw.txt"]})):
        grp_parser = group(grp, label)
        for name, func, text in (
                ("inspect", cmd_archive_inspect, "list parts, sizes and the free space an extract needs"),
                ("verify", cmd_archive_verify, "test every part's checksums; writes nothing"),
                ("extract", cmd_archive_extract,
                 "verify, then extract; with --delete the archive is removed afterwards (RAR: each part "
                 "once its files are out)")):
            p = add(grp_parser, name, func, text, examples(*ex_lines[name]))
            p.add_argument("archive", help=first_help)
            pw = p.add_mutually_exclusive_group()
            pw.add_argument("--password", help="archive password (visible to other programs; prefer the next two)")
            pw.add_argument("--password-stdin", action="store_true", help="read the password from the first stdin line")
            p.epilog += "\n\nThe password can also come from the EE_PASSWORD environment variable."
            if name != "verify":
                p.add_argument("--dest", help="extract into this folder (default: next to the archive, named after it)")
                p.add_argument("--delete", action="store_true",
                               help="delete the archive once it is extracted. RAR: each part goes once every file "
                                    "in it is out and a stopped run resumes when the same command is run again; "
                                    "other formats: the whole archive goes after a clean extraction")
                p.add_argument("--early-delete", action="store_true",
                               help="RAR only, with --delete: delete each part as soon as it is read. Needs less "
                                    "free space, but a stop or crash loses the file being extracted")
            if name == "extract":
                p.add_argument("--no-verify", action="store_true", help="skip the checksum pass before extracting")
                p.add_argument("--ignore-space", action="store_true", help="start even if free space looks too low")
                p.add_argument("--dry-run", action="store_true", help="check everything and print the plan; change nothing")
                p.add_argument("--yes", action="store_true", help="confirm --delete")
            if name != "inspect":
                p.add_argument("--background", action="store_true", help=background_help)

    isos = group("iso", "install a game from an ISO while freeing the ISO behind setup")
    p = add(isos, "status", cmd_iso_status, "check whether Windows has mounted an ISO",
            examples("iso status Game.iso", "--json iso status Game.iso"))
    p.add_argument("iso", help="the game ISO")

    p = add(isos, "inspect", cmd_iso_inspect, "files in the ISO and the free space an install needs",
            examples("iso inspect Game.iso", "iso inspect Game.iso --install-size-mb 52000 --buffer-gb 5",
                     "--json iso inspect Game.iso --files"))
    p.add_argument("iso", help="the game ISO (UDF, with setup.exe and .bin files)")
    p.add_argument("--install-size-mb", type=float, help="from setup: 'At least ... MB of free disk space is required'")
    p.add_argument("--buffer-gb", type=float, default=iso.DEFAULT_BUFFER_GB,
                   help=f"GB of ISO kept behind setup (default {iso.DEFAULT_BUFFER_GB})")
    p.add_argument("--files", action="store_true", help="also list every file")

    p = add(isos, "install", cmd_iso_install,
            "mount the ISO, run setup.exe and free the ISO behind it (admin terminal)",
            examples("iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --dry-run",
                     "iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --silent --yes",
                     "iso install Game.iso --install-dir \"D:\\Games\\Game\" --install-size-mb 52000 --silent "
                     "--delete-iso --yes",
                     "iso install Game.iso --no-free --no-setup        (mount only; send 'quit' to unmount)"))
    p.add_argument("iso", help="the game ISO")
    p.add_argument("--install-dir", help="folder setup installs into (required unless --no-free)")
    p.add_argument("--install-size-mb", type=float, help="from setup: 'At least ... MB of free disk space is required'")
    p.add_argument("--buffer-gb", type=float, default=iso.DEFAULT_BUFFER_GB,
                   help=f"GB of ISO kept behind setup (default {iso.DEFAULT_BUFFER_GB})")
    p.add_argument("--no-free", action="store_true", help="serve the ISO and log reads, but free nothing")
    p.add_argument("--no-setup", action="store_true", help="only mount; unmount on 'quit' (stdin) or Ctrl+C")
    p.add_argument("--silent", action="store_true",
                   help="run setup unattended: " + " ".join(SETUP_SILENT) + " /DIR=<install-dir>")
    p.add_argument("--setup-arg", action="append", default=[], help="extra argument for setup.exe (repeatable)")
    p.add_argument("--delete-iso", action="store_true", help="delete the ISO if setup fully succeeded")
    p.add_argument("--status-every", type=float, default=10, help="seconds between status lines (default 10)")
    p.add_argument("--dry-run", action="store_true", help="run every check and print the plan; mount nothing")
    p.add_argument("--yes", action="store_true", help="confirm freeing the ISO and --delete-iso")
    p.add_argument("--background", action="store_true", help=background_help)

    p = add(isos, "delete", cmd_iso_delete, "delete an ISO and its freeing record (no-op if already gone)",
            examples("iso delete Game.iso --dry-run", "iso delete Game.iso --yes"))
    p.add_argument("iso", help="the ISO to delete")
    p.add_argument("--dry-run", action="store_true", help="say what would be deleted")
    p.add_argument("--yes", action="store_true", help="confirm")
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = "--json" in argv or os.environ.get("EE_JSON", "") not in ("", "0")
    out = Out(as_json, quiet="-q" in argv or "--quiet" in argv)
    started = time.time()
    try:
        args = build_parser().parse_args(argv)
        if args.func is None:               # a group or nothing at all: show what's there
            if out.as_json:
                raise Stop(2, "Missing command.", fix=f"{args.parser.prog} --help")
            args.parser.print_help()
            return 0
        for name, default in (("verbose", False), ("progress_every", 2.0), ("background", False)):
            if not hasattr(args, name):
                setattr(args, name, default)
        args.argv = argv
        args.pw = read_password(args) if args.group in ("rar", "archive") else None
        jobs.watch_for_stop()
        result = args.func(args, out)
        code, result = result if isinstance(result, tuple) else (0 if result.get("ok") else 1, result)
        failed = False
    except Stop as e:
        failed = True
        out("error", e.msg, **({"fix": e.fix} if e.fix else {}))
        if e.fix and not out.as_json:
            print(f"  {e.fix}", file=sys.stderr)
        result, code = dict(e.extra, ok=False, error=e.msg, **({"fix": e.fix} if e.fix else {})), e.code
    except KeyboardInterrupt:
        out("error", "Stopped with Ctrl+C.")
        result, code, failed = {"ok": False, "error": "interrupted"}, 130, True
    result["duration_s"] = round(time.time() - started, 2)
    if out.as_json or not failed:
        out.result(code, result)
    return code


if __name__ == "__main__":
    sys.exit(main())
