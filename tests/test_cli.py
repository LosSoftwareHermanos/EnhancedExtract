"""End-to-end tests of cli.py: its contract (help, errors, JSON, exit codes) and the RAR
commands against real archives made with WinRAR's Rar.exe.

    python -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAR = r"C:\Program Files\WinRAR\Rar.exe"


def run(*args, stdin=None):
    return subprocess.run([sys.executable, os.path.join(APP, "cli.py"), *args], input=stdin,
                          capture_output=True, text=True, encoding="utf-8")


def cli(*args, stdin=None):
    """Run cli.py --json; returns (exit code, list of JSON events)."""
    p = run("--json", *args, stdin=stdin)
    return p.returncode, [json.loads(line) for line in p.stdout.splitlines()]


class Contract(unittest.TestCase):
    def test_no_arguments_shows_commands(self):
        p = run()
        self.assertEqual(p.returncode, 0)
        self.assertIn("Examples:", p.stdout)

    def test_every_command_help_has_examples(self):
        for cmd in (["system", "check"], ["system", "install-winfsp"], ["rar", "inspect"], ["rar", "verify"],
                    ["rar", "extract"], ["iso", "inspect"], ["iso", "install"], ["iso", "delete"]):
            p = run(*cmd, "--help")
            self.assertEqual(p.returncode, 0, cmd)
            self.assertIn("Examples:", p.stdout, cmd)

    def test_bad_arguments_are_json_with_a_fix(self):
        code, events = cli("rar", "extract")
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["type"], "result")
        self.assertIn("rar extract", events[-1]["fix"])

    def test_json_flag_works_after_the_command(self):
        p = run("system", "check", "--json")
        result = json.loads(p.stdout.splitlines()[-1])
        self.assertEqual(result["type"], "result")
        self.assertIn("unrar", result)

    def test_iso_delete_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.iso")
            open(path, "wb").close()
            self.assertEqual(cli("iso", "delete", path)[0], 6)
            self.assertEqual(cli("iso", "delete", path, "--dry-run")[0], 0)
            self.assertTrue(os.path.exists(path))
            self.assertEqual(cli("iso", "delete", path, "--yes")[0], 0)
            code, events = cli("iso", "delete", path, "--yes")
            self.assertEqual(code, 0)
            self.assertTrue(events[-1]["already_done"])


@unittest.skipUnless(os.path.isfile(RAR), "needs WinRAR's Rar.exe to build test archives")
class RarCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "Ünïcødé src")    # non-ASCII on purpose
        os.makedirs(self.src)
        for i in range(3):
            with open(os.path.join(self.src, f"f{i}.bin"), "wb") as f:
                f.write(os.urandom(300_000))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_set(self, name="Tëst game", *extra):
        subprocess.run([RAR, "a", "-v200k", "-ep1", "-idq", *extra,
                        os.path.join(self.tmp, name + ".rar"), self.src], check=True)
        return os.path.join(self.tmp, name + ".part1.rar")

    def assert_same_files(self, out_dir):
        for i in range(3):
            with open(os.path.join(self.src, f"f{i}.bin"), "rb") as a, \
                    open(os.path.join(out_dir, "Ünïcødé src", f"f{i}.bin"), "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_inspect_lists_every_part(self):
        code, events = cli("rar", "inspect", self.make_set())
        self.assertEqual(code, 0)
        archive = next(e for e in events if e["type"] == "archive")
        self.assertEqual(len(archive["volumes"]), 5)
        self.assertTrue(events[-1]["ok"])

    def test_delete_needs_yes(self):
        first = self.make_set()
        code, events = cli("rar", "extract", first, "--delete")
        self.assertEqual(code, 6)
        self.assertTrue(events[-1]["fix"].endswith("--yes"))
        self.assertTrue(os.path.exists(first))

    def test_dry_run_changes_nothing(self):
        first = self.make_set()
        code, events = cli("rar", "extract", first, "--delete", "--dry-run")
        self.assertEqual(code, 0)
        plan = next(e for e in events if e["type"] == "plan")
        self.assertEqual(len(plan["deletes"]), 5)
        self.assertTrue(os.path.exists(first))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "Tëst game")))

    def test_text_mode_keeps_stdout_for_data(self):
        p = run("rar", "verify", self.make_set())
        self.assertEqual(p.returncode, 0)
        self.assertIn("Verifying", p.stderr)
        self.assertNotIn("Verifying", p.stdout)
        self.assertIn("parts: 5", p.stdout)

    def test_extract_with_delete_removes_parts_and_keeps_data(self):
        first = self.make_set()
        dest = os.path.join(self.tmp, "out")
        code, events = cli("rar", "extract", first, "--dest", dest, "--delete", "--yes")
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["parts_left"], 0)
        self.assertFalse([f for f in os.listdir(self.tmp) if f.endswith(".rar")])
        self.assert_same_files(dest)
        phases = {e["phase"] for e in events if e["type"] == "progress"}
        self.assertEqual(phases, {"verifying", "extracting"})
        # retried after success: the parts are gone, but it reports done instead of failing
        code, events = cli("rar", "extract", first, "--dest", dest, "--delete", "--yes")
        self.assertEqual(code, 0, events[-1])
        self.assertTrue(events[-1]["already_done"])

    def test_password(self):
        first = self.make_set("locked", "-hpsecret")
        code, _ = cli("rar", "inspect", first)
        self.assertEqual(code, 3)
        code, _ = cli("rar", "inspect", first, "--password", "wrong")
        self.assertEqual(code, 3)
        dest = os.path.join(self.tmp, "out")
        code, events = cli("rar", "extract", first, "--dest", dest, "--password-stdin", stdin="secret\n")
        self.assertEqual(code, 0, events[-1])
        self.assert_same_files(dest)

    def test_corrupt_part_fails_verify_and_deletes_nothing(self):
        first = self.make_set()
        part3 = first.replace("part1", "part3")
        with open(part3, "r+b") as f:
            f.seek(100_000)
            f.write(b"\0" * 1000)
        code, events = cli("rar", "extract", first, "--dest", os.path.join(self.tmp, "out"), "--delete", "--yes")
        self.assertEqual(code, 1)
        self.assertEqual(events[-1]["parts_left"], 5)


if __name__ == "__main__":
    unittest.main()
