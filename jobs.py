"""Background jobs for the terminal version.

A long command run with --background starts a detached copy of itself that writes its
JSON events to jobs/<id>.jsonl and returns at once. `jobs status|wait|logs|stop` read that
file, so an agent can check on a game install across many short tool calls.

Stopping: `jobs stop` drops a <id>.stop file; the job notices within half a second and
stops as if Ctrl+C was pressed (and unmounts / kills UnRAR cleanly)."""
import _thread
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes

import paths

JOBS_DIR = os.path.join(paths.DATA_DIR, "jobs")
ENV_ID = "EE_JOB_ID"
STILL_ACTIVE = 259
DETACHED = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _file(job_id, ext):
    return os.path.join(JOBS_DIR, f"{job_id}.{ext}")


def cli_command():
    if paths.FROZEN:
        return [sys.executable, "--cli"]
    return [sys.executable, os.path.join(paths.APP_DIR, "cli.py")]


def start(argv, password=None):
    """Start `cli.py --json <argv>` detached. Returns the job id."""
    os.makedirs(JOBS_DIR, exist_ok=True)
    job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    env = dict(os.environ, **{ENV_ID: job_id})
    if password:
        env["EE_PASSWORD"] = password       # never on the command line
    cmd = cli_command() + ["--json"] + argv
    with open(_file(job_id, "jsonl"), "w", encoding="utf-8") as out, \
            open(_file(job_id, "err"), "w", encoding="utf-8") as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=env,
                                cwd=paths.APP_DIR, creationflags=DETACHED, close_fds=True)
    with open(_file(job_id, "json"), "w", encoding="utf-8") as f:
        json.dump({"id": job_id, "argv": argv, "pid": proc.pid, "started": time.time()}, f)
    return job_id


def watch_for_stop():
    """In a job: turn a stop request into Ctrl+C for the main thread."""
    job_id = os.environ.get(ENV_ID)
    if not job_id:
        return

    def loop():
        stop = _file(job_id, "stop")
        while True:
            time.sleep(0.5)
            if os.path.exists(stop):
                try:
                    os.remove(stop)
                except OSError:
                    pass
                _thread.interrupt_main()

    threading.Thread(target=loop, daemon=True).start()


def _alive(pid):
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    handle = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def _meta(job_id):
    try:
        with open(_file(job_id, "json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def events(job_id):
    """All complete events the job has written so far."""
    out = []
    try:
        with open(_file(job_id, "jsonl"), encoding="utf-8") as f:
            for line in f:
                if line.endswith("\n"):
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def ids():
    """Job ids, newest first."""
    try:
        names = os.listdir(JOBS_DIR)
    except OSError:
        return []
    return sorted((n[:-5] for n in names if n.endswith(".json")), reverse=True)


def resolve(job_id):
    """A full id, from a full id, a unique prefix/suffix, or None for the newest job."""
    all_ids = ids()
    if not job_id:
        return all_ids[0] if all_ids else None
    if job_id in all_ids:
        return job_id
    hits = [i for i in all_ids if i.startswith(job_id) or i.endswith(job_id)]
    return hits[0] if len(hits) == 1 else None


def snapshot(job_id):
    """Where a job stands, small enough to read every poll."""
    meta = _meta(job_id)
    if meta is None:
        return None
    evs = events(job_id)
    result = next((e for e in reversed(evs) if e.get("type") == "result"), None)
    if result:
        state = "done" if result.get("exit_code") == 0 else "failed"
    elif _alive(meta["pid"]):
        state = "running"
    else:
        state = "died"
    last = lambda t: next((e for e in reversed(evs) if e.get("type") == t), None)
    snap = {"id": job_id, "state": state, "command": " ".join(meta["argv"]), "argv": meta["argv"],
            "elapsed_s": round((result or {}).get("ts", time.time()) - meta["started"], 1)}
    progress = last("progress") or last("status")
    if progress and state == "running":
        snap["progress"] = {k: v for k, v in progress.items() if k not in ("type", "ts")}
    warnings = [e["msg"] for e in evs if e.get("type") == "warning"]
    if warnings:
        snap["warnings"] = warnings[-5:]
    if result:
        snap["job_exit_code"] = result.get("exit_code")
        snap["result"] = {k: v for k, v in result.items() if k not in ("type", "ts", "schema")}
    elif state == "died":
        try:
            with open(_file(job_id, "err"), encoding="utf-8", errors="replace") as f:
                snap["stderr"] = f.read()[-1500:]
        except OSError:
            pass
    return snap


def request_stop(job_id):
    open(_file(job_id, "stop"), "w").close()
