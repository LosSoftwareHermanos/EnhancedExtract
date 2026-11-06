"""End-to-end tests of cli.py: its contract (help, errors, JSON, exit codes), the RAR
commands against real archives made with WinRAR's Rar.exe, and the background-job flow an
agent uses. Jobs and logs go to a temporary EE_DATA_DIR, not the app folder.

    python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAR = r"C:\Program Files\WinRAR\Rar.exe"
DATA = tempfile.mkdtemp(prefix="ee-test-data-")
ENV = dict(os.environ, EE_DATA_DIR=DATA)
ENV.pop("EE_JSON", None)
ENV.pop("EE_PASSWORD", None)


def tearDownModule():
    shutil.rmtree(DATA, ignore_errors=True)


def run(*args, stdin=None):
    engine = os.environ.get("EE_TEST_ENGINE")
    command = [engine, "--cli"] if engine else [sys.executable, os.path.join(APP, "cli.py")]
    return subprocess.run([*command, *args], input=stdin, env=ENV,
                          capture_output=True, text=True, encoding="utf-8")


def cli(*args, stdin=None):
    """Run cli.py --json; returns (exit code, list of JSON events)."""
    p = run("--json", *args, stdin=stdin)
    return p.returncode, [json.loads(line) for line in p.stdout.splitlines()]


class Contract(unittest.TestCase):
    def test_no_arguments_shows_commands_and_agent_flow(self):
        p = run()
        self.assertEqual(p.returncode, 0)
        self.assertIn("Typical agent flow:", p.stdout)
        self.assertIn("Examples:", p.stdout)

    def test_every_command_help_has_examples(self):
        code, events = cli("schema")
        self.assertEqual(code, 0)
        for command in events[0]["commands"]:
            p = run(*command["command"].split(), "--help")
            self.assertEqual(p.returncode, 0, command["command"])
            self.assertIn("Examples:", p.stdout, command["command"])

    def test_schema_describes_every_command_once(self):
        code, events = cli("schema")
        spec = events[0]
        names = [c["command"] for c in spec["commands"]]
        for expected in ("scan", "rar extract", "iso install", "jobs wait", "jobs stop"):
            self.assertIn(expected, names)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(c["examples"] for c in spec["commands"]))
        self.assertIn("7", spec["exit_codes"])
        flags = [a["name"] for c in spec["commands"] for a in c["args"]]
        self.assertNotIn("--json", flags)        # listed once, under global_flags

    def test_bad_arguments_are_json_with_a_fix(self):
        code, events = cli("rar", "extract")
        self.assertEqual(code, 2)
        self.assertEqual(events[-1]["type"], "result")
        self.assertIn("rar extract", events[-1]["fix"])

    def test_abbreviated_flags_are_rejected(self):
        self.assertEqual(cli("iso", "delete", "x.iso", "--dry")[0], 2)

    def test_json_flag_works_after_the_command(self):
        p = run("system", "check", "--json")
        result = json.loads(p.stdout.splitlines()[-1])
        self.assertEqual(result["type"], "result")
        self.assertIn("unrar", result)

    def test_unknown_job_says_how_to_list_jobs(self):
        code, events = cli("jobs", "status", "nope")
        self.assertEqual(code, 2)
        self.assertIn("jobs list", events[-1]["fix"])

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

    def test_inspect_lists_every_part_and_the_next_step(self):
        code, events = cli("rar", "inspect", self.make_set())
        self.assertEqual(code, 0)
        archive = next(e for e in events if e["type"] == "archive")
        self.assertEqual(len(archive["volumes"]), 5)
        self.assertIn("rar extract", events[-1]["next"])
        self.assertIn("--dry-run", events[-1]["next"])

    def test_scan_finds_sets_and_missing_parts(self):
        first = self.make_set()
        os.remove(first.replace("part1", "part4"))
        code, events = cli("scan", self.tmp)
        self.assertEqual(code, 0)
        found = next(e for e in events if e["type"] == "rar_set")
        self.assertEqual(os.path.normcase(found["first"]), os.path.normcase(first))
        self.assertEqual(found["missing"], [4])

    def test_delete_needs_yes(self):
        first = self.make_set()
        code, events = cli("rar", "extract", first, "--delete")
        self.assertEqual(code, 6)
        self.assertTrue(events[-1]["fix"].endswith("--yes"))
        self.assertTrue(os.path.exists(first))

    def test_dry_run_changes_nothing_and_says_what_to_run(self):
        first = self.make_set()
        code, events = cli("rar", "extract", first, "--delete", "--dry-run")
        self.assertEqual(code, 0)
        plan = next(e for e in events if e["type"] == "plan")
        self.assertEqual(len(plan["deletes"]), 5)
        self.assertTrue(events[-1]["needs_yes"])
        self.assertIn("--background", events[-1]["next"])
        self.assertTrue(os.path.exists(first))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "Tëst game")))

    def test_text_mode_keeps_stdout_for_data(self):
        p = run("rar", "verify", self.make_set())
        self.assertEqual(p.returncode, 0)
        self.assertIn("Verifying", p.stderr)
        self.assertNotIn("Verifying", p.stdout)
        self.assertIn("parts: 5", p.stdout)

    def test_output_stays_small_unless_verbose(self):
        first = self.make_set()
        code, quiet = cli("rar", "verify", first)
        self.assertEqual(code, 0)
        self.assertLess(len(quiet), 15, [e["type"] for e in quiet])
        self.assertFalse(any("f1.bin" in e.get("msg", "") for e in quiet))
        last = [e for e in quiet if e["type"] == "progress"][-1]
        self.assertEqual(last["overall"], 100.0)
        self.assertEqual(last["files_done"], last["files"])     # 3 files + their folder
        code, verbose = cli("rar", "verify", first, "--verbose")
        self.assertTrue(any("f1.bin" in e.get("msg", "") for e in verbose))

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

    def test_background_job_end_to_end(self):
        """What an agent does: start in the background, poll with short waits, read the result."""
        first = self.make_set()
        dest = os.path.join(self.tmp, "out")
        started = time.time()
        code, events = cli("rar", "extract", first, "--dest", dest, "--delete", "--yes", "--background",
                           "--password-stdin", stdin="\n")
        self.assertEqual(code, 0, events[-1])
        self.assertLess(time.time() - started, 5)          # returns at once, not after the job
        job = events[-1]["job"]
        self.assertIn("jobs wait", events[-1]["next"])
        for _ in range(60):
            code, events = cli("jobs", "wait", job, "--timeout", "2")
            if code != 7:
                break
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["state"], "done")
        self.assertEqual(events[-1]["result"]["parts_left"], 0)
        self.assertEqual(events[-1]["progress"]["overall"], 100)
        self.assert_same_files(dest)
        code, events = cli("jobs", "logs", job, "--type", "result")
        self.assertEqual(events[-1]["shown"], 1)
        code, events = cli("jobs", "list")
        self.assertIn(job, [e.get("id") for e in events if e["type"] == "job"])

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

    def test_background_job_gets_the_password_without_the_command_line(self):
        first = self.make_set("locked", "-hpsecret")
        dest = os.path.join(self.tmp, "out")
        code, events = cli("rar", "extract", first, "--dest", dest, "--background", "--password-stdin",
                           stdin="secret\n")
        self.assertEqual(code, 0, events[-1])
        job = events[-1]["job"]
        with open(os.path.join(DATA, "jobs", job + ".json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())
        code, events = cli("jobs", "wait", job, "--timeout", "60")
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


def seven_zip():
    sys.path.insert(0, APP)
    try:
        import sevenzip
        return sevenzip.find_7z()
    except Exception:
        return None
    finally:
        sys.path.remove(APP)


@unittest.skipUnless(seven_zip(), "needs 7-Zip (7z.exe) to read and build test archives")
class OtherFormatsCli(unittest.TestCase):
    """zip, 7z, tar.gz, split sets and passwords, through 7-Zip. Zip and tar.gz test archives are
    built with Python's own libraries, so they do not depend on the tool being tested."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(os.path.join(self.src, "Ünï"))
        self.payload = {"a.txt": b"hello", os.path.join("Ünï", "big.bin"): os.urandom(2_500_000)}
        for name, data in self.payload.items():
            with open(os.path.join(self.src, name), "wb") as f:
                f.write(data)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def zip(self, name="Pack.zip"):
        import zipfile
        path = os.path.join(self.tmp, name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n in self.payload:
                z.write(os.path.join(self.src, n), n.replace(os.sep, "/"))
        return path

    def tar_gz(self, name="Pack.tar.gz"):
        import tarfile
        path = os.path.join(self.tmp, name)
        with tarfile.open(path, "w:gz") as t:
            t.add(self.src, arcname=".")
        return path

    def seven(self, *flags, name="Pack.7z"):
        path = os.path.join(self.tmp, name)
        subprocess.run([seven_zip(), "a", *flags, path, os.path.join(self.src, "*"), "-bso0", "-bsp0"], check=True)
        return path

    def assert_extracted(self, out_dir):
        for name, data in self.payload.items():
            with open(os.path.join(out_dir, name), "rb") as f:
                self.assertEqual(f.read(), data, name)

    def test_zip_extracts_with_the_same_result_fields_as_rar(self):
        out = os.path.join(self.tmp, "out")
        code, events = cli("archive", "extract", self.zip(), "--dest", out)
        self.assertEqual(code, 0, events[-1])
        self.assert_extracted(out)
        result = events[-1]
        self.assertEqual((result["dest"], result["parts"], result["parts_left"]), (out, 1, 1))
        self.assertEqual({e["phase"] for e in events if e["type"] == "progress"}, {"verifying", "extracting"})
        self.assertEqual(events[-2]["type"], "progress")
        self.assertEqual(events[-2]["overall"], 100.0)

    def test_rar_group_takes_other_formats_too(self):
        out = os.path.join(self.tmp, "out")
        self.assertEqual(cli("rar", "extract", self.zip(), "--dest", out)[0], 0)
        self.assert_extracted(out)

    def test_7z_and_tar_gz(self):
        for make in (self.seven, self.tar_gz):
            out = os.path.join(self.tmp, "out-" + make.__name__)
            code, events = cli("archive", "extract", make(), "--dest", out)
            self.assertEqual(code, 0, (make.__name__, events[-1]))
            self.assert_extracted(out)

    def test_tar_gz_counts_the_files_inside_the_tar(self):
        code, events = cli("archive", "inspect", self.tar_gz())
        self.assertEqual(code, 0)
        archive = next(e for e in events if e["type"] == "archive")
        self.assertEqual(archive["files"], 2)       # not 1 (the tar) and not counting folders
        self.assertEqual(archive["format"], "gzip")

    def test_default_destination_is_named_after_the_archive(self):
        for name, folder in (("Pack.zip", "Pack"), ("Pack.tar.gz", "Pack"), ("My.Game.v2.zip", "My.Game.v2")):
            path = self.zip(name) if name.endswith("zip") else self.tar_gz(name)
            code, events = cli("archive", "inspect", path)
            self.assertEqual(events[-1]["dest"], os.path.join(self.tmp, folder), name)

    def test_split_set_opens_from_any_piece_and_missing_pieces_are_named(self):
        self.seven("-v1m", name="Split.7z")
        pieces = sorted(f for f in os.listdir(self.tmp) if f.startswith("Split.7z."))
        self.assertGreaterEqual(len(pieces), 3)
        code, events = cli("archive", "inspect", os.path.join(self.tmp, pieces[-1]))
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(len(next(e for e in events if e["type"] == "archive")["volumes"]), len(pieces))
        found = next(e for e in cli("scan", self.tmp)[1] if e["type"] == "archive_set" and "Split" in e["first"])
        self.assertTrue(found["first"].endswith("Split.7z.001"))
        os.remove(os.path.join(self.tmp, pieces[1]))
        code, events = cli("archive", "inspect", os.path.join(self.tmp, pieces[0]))
        self.assertEqual(code, 1)
        self.assertIn("Missing parts", events[-1]["error"])

    def test_delete_needs_yes_and_removes_every_piece_only_after_success(self):
        self.seven("-v1m", name="Split.7z")
        first = os.path.join(self.tmp, "Split.7z.001")
        pieces = [f for f in os.listdir(self.tmp) if f.startswith("Split.7z.")]
        code, events = cli("archive", "extract", first, "--delete")
        self.assertEqual(code, 6)
        self.assertTrue(events[-1]["fix"].endswith("--yes"))
        code, events = cli("archive", "extract", first, "--delete", "--dry-run")
        plan = next(e for e in events if e["type"] == "plan")
        self.assertEqual(len(plan["deletes"]), len(pieces))
        self.assertTrue(events[-1]["needs_yes"])
        self.assertTrue(all(os.path.exists(os.path.join(self.tmp, p)) for p in pieces))
        out = os.path.join(self.tmp, "out")
        code, events = cli("archive", "extract", first, "--dest", out, "--delete", "--yes")
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["parts_left"], 0)
        self.assertFalse([f for f in os.listdir(self.tmp) if f.startswith("Split.7z.")])
        self.assert_extracted(out)
        code, events = cli("archive", "extract", first, "--dest", out, "--delete", "--yes")   # retried after success
        self.assertEqual(code, 0, events[-1])
        self.assertTrue(events[-1]["already_done"])

    def test_a_corrupt_archive_is_never_deleted(self):
        path = self.seven()
        with open(path, "rb") as f:
            data = bytearray(f.read())
        data[len(data) // 2] ^= 0xFF
        with open(path, "wb") as f:
            f.write(data)
        code, events = cli("archive", "extract", path, "--dest", os.path.join(self.tmp, "out"), "--delete", "--yes")
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(path))

    def test_password_goes_through_stdin_and_a_wrong_one_is_exit_3(self):
        path = self.seven("-pSECRET", "-mhe=on")
        code, events = cli("archive", "inspect", path)
        self.assertEqual(code, 3)
        self.assertIn("--password-stdin", events[-1]["fix"])
        self.assertEqual(cli("archive", "inspect", path, "--password-stdin", stdin="WRONG\n")[0], 3)
        out = os.path.join(self.tmp, "out")
        code, events = cli("archive", "extract", path, "--dest", out, "--password-stdin", stdin="SECRET\n")
        self.assertEqual(code, 0, events[-1])
        self.assert_extracted(out)

    def test_wrong_password_on_a_zip_whose_names_are_open_is_caught_before_writing(self):
        path = self.seven("-tzip", "-pSECRET", name="Locked.zip")
        out = os.path.join(self.tmp, "out")
        self.assertEqual(cli("archive", "extract", path, "--dest", out)[0], 3)       # names open, still asks
        code, events = cli("archive", "extract", path, "--dest", out, "--password-stdin", stdin="WRONG\n")
        self.assertEqual(code, 3)
        self.assertFalse(os.path.exists(os.path.join(out, "a.txt")))

    def test_early_delete_is_for_rar_only(self):
        code, events = cli("archive", "extract", self.zip(), "--delete", "--early-delete")
        self.assertEqual(code, 2)
        self.assertNotIn("--early-delete", events[-1]["fix"])

    def test_not_an_archive_fails_cleanly(self):
        path = os.path.join(self.tmp, "junk.zip")
        with open(path, "wb") as f:
            f.write(b"this is not a zip")
        code, events = cli("archive", "inspect", path)
        self.assertEqual(code, 1)
        self.assertEqual(events[-1]["type"], "result")

    def test_scan_lists_other_formats_next_to_rar_sets(self):
        self.zip()
        self.tar_gz()
        code, events = cli("scan", self.tmp)
        names = {os.path.basename(e["first"]): e["format"] for e in events if e["type"] == "archive_set"}
        self.assertEqual(names, {"Pack.zip": "zip", "Pack.tar.gz": "gz"})
        self.assertEqual(events[-1]["archives"], 2)
        self.assertIn("archive inspect", next(e for e in events if e["type"] == "archive_set")["next"])

    def test_scan_reports_missing_classic_zip_pieces(self):
        # Scanning only uses names; it must warn before the user opens an incomplete set.
        for name in ("Split.z01", "Split.z03", "Split.zip"):
            with open(os.path.join(self.tmp, name), "wb") as f:
                f.write(b"part")
        code, events = cli("scan", self.tmp)
        found = [e for e in events if e["type"] == "archive_set"]
        self.assertEqual(code, 0)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["missing"], [2])
        self.assertEqual(found[0]["first"], os.path.join(self.tmp, "Split.zip"))

    def test_compressed_tar_variants_and_standalone_streams(self):
        import bz2
        import gzip
        import lzma
        import tarfile
        for suffix, mode in (("tar", "w"), ("tgz", "w:gz"), ("tar.bz2", "w:bz2"), ("txz", "w:xz")):
            with self.subTest(format=suffix):
                path = os.path.join(self.tmp, "Bundle." + suffix)
                with tarfile.open(path, mode) as archive:
                    archive.add(self.src, arcname=".")
                dest = os.path.join(self.tmp, "out-" + suffix)
                code, events = cli("archive", "extract", path, "--dest", dest)
                self.assertEqual(code, 0, events[-1])
                self.assert_extracted(dest)
                self.assertGreaterEqual(events[-1]["unpacked"], sum(map(len, self.payload.values())))
                self.assertEqual(events[-1]["files"], len(self.payload))
                self.assertTrue(os.path.isfile(path))
                self.assertFalse(os.path.exists(os.path.join(dest, "Bundle.tar")))
        for suffix, compress in (("gz", gzip.compress), ("bz2", bz2.compress), ("xz", lzma.compress)):
            with self.subTest(format=suffix):
                data = self.payload["a.txt"]
                path = os.path.join(self.tmp, "single.txt." + suffix)
                with open(path, "wb") as f:
                    f.write(compress(data))
                dest = os.path.join(self.tmp, "out-" + suffix)
                code, events = cli("archive", "extract", path, "--dest", dest)
                self.assertEqual(code, 0, events[-1])
                self.assertEqual(events[-1]["unpacked"], len(data))
                with open(os.path.join(dest, "single.txt"), "rb") as f:
                    self.assertEqual(f.read(), data)

    def test_zip_background_job_preserves_whole_archive_progress(self):
        path = self.zip()
        dest = os.path.join(self.tmp, "background-out")
        code, events = cli("archive", "extract", path, "--dest", dest, "--background")
        self.assertEqual(code, 0, events[-1])
        job = events[-1]["job"]
        code, events = cli("jobs", "wait", job, "--timeout", "30")
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["result"]["format"], "zip")
        self.assertTrue(events[-1]["progress"]["whole"])
        self.assert_extracted(dest)
        self.assertTrue(os.path.isfile(path))

    def test_zstd_stream_and_compressed_tar(self):
        try:
            from compression import zstd
        except ImportError:
            self.skipTest("Python 3.14 compression.zstd is needed to create these independent fixtures")
        import tarfile
        data = self.payload["a.txt"]
        path = os.path.join(self.tmp, "single.txt.zst")
        with open(path, "wb") as f:
            f.write(zstd.compress(data))
        dest = os.path.join(self.tmp, "out-zstd")
        code, events = cli("archive", "extract", path, "--dest", dest)
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["unpacked"], len(data))
        with open(os.path.join(dest, "single.txt"), "rb") as f:
            self.assertEqual(f.read(), data)
        path = os.path.join(self.tmp, "Bundle.tar.zst")
        with tarfile.open(path, "w:zst") as archive:
            archive.add(self.src, arcname=".")
        dest = os.path.join(self.tmp, "out-tar-zstd")
        code, events = cli("archive", "extract", path, "--dest", dest)
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["files"], len(self.payload))
        self.assert_extracted(dest)

    def test_wim_extracts_unicode_files(self):
        path = self.seven("-twim", name="Image.wim")
        dest = os.path.join(self.tmp, "out-wim")
        code, events = cli("archive", "extract", path, "--dest", dest)
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["format"], "wim")
        self.assert_extracted(dest)

    @unittest.skipUnless(shutil.which("makecab.exe"), "needs Windows makecab to build a CAB fixture")
    def test_cab_from_windows_makecab(self):
        path = os.path.join(self.tmp, "Payload.cab")
        subprocess.run(["makecab.exe", "/D", "CompressionType=LZX", os.path.join(self.src, "a.txt"), path],
                       check=True, capture_output=True)
        dest = os.path.join(self.tmp, "out-cab")
        code, events = cli("archive", "extract", path, "--dest", dest)
        self.assertEqual(code, 0, events[-1])
        with open(os.path.join(dest, "a.txt"), "rb") as f:
            self.assertEqual(f.read(), self.payload["a.txt"])

    def test_bundled_7zip_works_without_a_system_install(self):
        from unittest.mock import patch
        import sevenzip
        bundled = os.path.join(APP, "deps", "7zip", "7z.exe")
        if not os.path.isfile(bundled):
            self.skipTest("bundled 7-Zip is absent from this source checkout")
        with patch.object(sevenzip, "SYSTEM_DIRS", []):
            self.assertEqual(os.path.normcase(sevenzip.find_7z()), os.path.normcase(bundled))
            for make in (self.zip, self.tar_gz):
                info = sevenzip.inspect(make())
                dest = os.path.join(self.tmp, "bundled-" + make.__name__)
                runner = sevenzip.Runner(log=lambda _: None, progress=lambda *args: None)
                runner.verify(info)
                runner.extract(info, dest)
                self.assert_extracted(dest)


@unittest.skipUnless(os.path.isfile(RAR), "needs WinRAR's Rar.exe to build test archives")
class ResumableDelete(unittest.TestCase):
    """Delete mode stopped partway, then resumed by running the same command again.

    The set: 5 parts of 1 MB, stored, with b.bin running across parts 1-3 and c.bin across
    parts 3-4. The run is stopped from inside (UnRAR killed) when it reaches a given part."""

    FILES = {"a.txt": 100_000, "b.bin": 2_500_000, "c.bin": 700_000, "d.bin": 900_000}

    def setUp(self):
        sys.path.insert(0, APP)
        import extractor
        self.ex = extractor
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src)
        for name, size in self.FILES.items():
            with open(os.path.join(self.src, name), "wb") as f:
                f.write(os.urandom(size))
        subprocess.run([RAR, "a", "-m0", "-v1m", "-ep1", "-idq", os.path.join(self.tmp, "set.rar"),
                        *[os.path.join(self.src, n) for n in self.FILES]], check=True)
        self.first = os.path.join(self.tmp, "set.part1.rar")
        self.dest = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def parts(self):
        return sorted(f for f in os.listdir(self.tmp) if f.endswith(".rar"))

    def stop_at(self, part, mode):
        info = self.ex.inspect(self.first)
        runner = None

        def progress(pct, at, total):
            if at >= part:
                runner.stop()
        runner = self.ex.Runner(log=lambda t: None, progress=progress)
        with self.assertRaises(self.ex.ExtractError):
            runner.extract(info, self.dest, True, mode)

    def resume(self, path=None):
        return cli("rar", "extract", path or self.first, "--delete", "--yes")

    def assert_extracted(self, skip=()):
        for name in self.FILES:
            if name in skip:
                continue
            with open(os.path.join(self.src, name), "rb") as a, open(os.path.join(self.dest, name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_safe_mode_keeps_every_part_of_a_file_still_being_extracted(self):
        self.stop_at(3, self.ex.SAFE)               # inside b.bin, which started in part 1
        self.assertEqual(len(self.parts()), 5)       # nothing of b.bin was deleted
        code, events = self.resume()
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(self.parts(), [])
        self.assertEqual(events[-1]["lost"], [])
        self.assert_extracted()
        self.assertFalse(os.path.exists(self.ex.journal_path(self.first)))

    def test_resume_after_parts_were_deleted_skips_the_finished_files(self):
        self.stop_at(4, self.ex.SAFE)               # b.bin done, parts 1-2 deleted, inside c.bin
        self.assertEqual(self.parts(), ["set.part3.rar", "set.part4.rar", "set.part5.rar"])
        code, events = cli("rar", "extract", self.first, "--delete", "--dry-run")
        self.assertEqual(code, 0, events[-1])
        self.assertTrue(events[-1]["resume"])
        self.assertEqual(events[-1]["dest"], self.dest)
        # any part left works as the starting point, as from Explorer
        code, events = self.resume(os.path.join(self.tmp, "set.part3.rar"))
        self.assertEqual(code, 0, events[-1])
        self.assertTrue(any("Resuming" in e.get("msg", "") for e in events))
        self.assertEqual(self.parts(), [])
        self.assert_extracted()

    def test_early_mode_loses_only_the_file_split_across_a_deleted_part(self):
        self.stop_at(3, self.ex.EARLY)              # parts 1-2 gone with the start of b.bin
        self.assertEqual(self.parts(), ["set.part3.rar", "set.part4.rar", "set.part5.rar"])
        code, events = self.resume()
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["lost"], ["b.bin"])
        self.assertFalse(os.path.exists(os.path.join(self.dest, "b.bin")))
        self.assert_extracted(skip={"b.bin"})

    def test_safe_mode_needs_room_for_the_largest_file_early_mode_for_one_part(self):
        info = self.ex.inspect(self.first)
        safe = self.ex.space_needed(info, self.dest, True, self.ex.SAFE) - self.ex.SAFETY_MARGIN
        early = self.ex.space_needed(info, self.dest, True, self.ex.EARLY) - self.ex.SAFETY_MARGIN
        keep = self.ex.space_needed(info, self.dest, False) - self.ex.SAFETY_MARGIN
        self.assertLess(early, safe)
        self.assertLess(safe, keep)
        self.assertGreaterEqual(safe, 2_500_000)    # b.bin's three parts are held until it is out

    def test_solid_set_deletes_nothing_until_the_end_in_safe_mode(self):
        solid = os.path.join(self.tmp, "solid.rar")
        subprocess.run([RAR, "a", "-s", "-m1", "-v1m", "-ep1", "-idq", solid,
                        *[os.path.join(self.src, n) for n in self.FILES]], check=True)
        info = self.ex.inspect(os.path.join(self.tmp, "solid.part1.rar"))
        layout = info.layout()
        self.assertTrue(layout.solid)
        self.assertEqual(self.ex.deletable_parts(layout, 3, self.ex.SAFE), [])


def winfsp_ready():
    sys.path.insert(0, APP)
    import isocore
    return isocore.winfsp_installed() and importlib.util.find_spec("fuse") is not None


@unittest.skipUnless(winfsp_ready(), "needs WinFsp and fusepy (python -m pip install fusepy)")
class IsoJob(unittest.TestCase):
    """Mount a real UDF ISO in the background, read through the drive, stop the job."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.src = os.path.join(cls.tmp, "src")
        os.makedirs(os.path.join(cls.src, "Data"))
        with open(os.path.join(cls.src, "setup.exe"), "wb") as f:
            f.write(b"MZ not a real setup")
        with open(os.path.join(cls.src, "Data", "game.bin"), "wb") as f:
            f.write(os.urandom(2_000_000))
        cls.iso = os.path.join(cls.tmp, "test.iso")
        script = os.path.join(cls.tmp, "mkiso.ps1")
        with open(script, "w", encoding="utf-8") as f:
            f.write(MKISO_PS1)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                        "-Src", cls.src, "-Out", cls.iso], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_mount_in_background_then_stop(self):
        code, events = cli("iso", "install", self.iso, "--no-free", "--no-setup", "--background")
        self.assertEqual(code, 0, events[-1])
        job = events[-1]["job"]
        letter = None
        for _ in range(60):
            _, logs = cli("jobs", "logs", job, "--type", "mounted")
            if logs[0]["type"] == "job_event":
                letter = logs[0]["event"]["letter"]
                break
            time.sleep(0.5)
        self.assertIsNotNone(letter, "drive never mounted")
        with open(os.path.join(letter + os.sep, "Data", "game.bin"), "rb") as a, \
                open(os.path.join(self.src, "Data", "game.bin"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        code, events = cli("jobs", "stop", job)
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["state"], "done")
        self.assertFalse(os.path.exists(letter + os.sep))


MKISO_PS1 = r"""
param([string]$Src, [string]$Out)
$fs = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fs.FileSystemsToCreate = 4
$fs.UDFRevision = 0x102
$fs.FreeMediaBlocks = 0
$fs.VolumeName = "TEST"
$fs.Root.AddTree($Src, $false)
$stream = $fs.CreateResultImage().ImageStream
Add-Type -TypeDefinition @"
using System; using System.IO; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes;
public static class IsoWriter { public static void Save(object s, string path) {
  IStream st = (IStream)s; byte[] buf = new byte[1 << 20]; IntPtr n = Marshal.AllocHGlobal(4);
  using (var f = File.Create(path)) { while (true) { st.Read(buf, buf.Length, n);
    int got = Marshal.ReadInt32(n); if (got <= 0) break; f.Write(buf, 0, got); } }
  Marshal.FreeHGlobal(n); } }
"@
[IsoWriter]::Save($stream, $Out)
"""


if __name__ == "__main__":
    unittest.main()
