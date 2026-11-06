"""Job snapshots keep the last recorded progress after work ends."""
import unittest
from unittest.mock import patch

import jobs


class JobProgress(unittest.TestCase):
    def test_terminal_snapshots_preserve_recorded_progress(self):
        meta = {"argv": ["rar", "extract", "demo.rar"], "pid": 1, "started": 10}
        progress = {"type": "progress", "ts": 12, "overall": 43.5,
                    "phase": "extracting", "part": 3, "parts": 5}
        for code, state in ((0, "done"), (1, "failed"), (130, "failed"), (None, "died")):
            with self.subTest(code=code):
                events = [progress]
                if code is not None:
                    events.append({"type": "result", "ts": 13, "exit_code": code})
                with patch.object(jobs, "_meta", return_value=meta), \
                     patch.object(jobs, "events", return_value=events), \
                     patch.object(jobs, "_alive", return_value=False):
                    snapshot = jobs.snapshot("fixture")
                self.assertEqual(snapshot["state"], state)
                self.assertEqual(snapshot.get("progress", {}).get("overall"), 43.5)
                self.assertEqual(snapshot["progress"]["part"], 3)
                self.assertNotIn("ts", snapshot["progress"])
