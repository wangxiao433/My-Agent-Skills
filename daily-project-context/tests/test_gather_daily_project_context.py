import importlib.util
import os
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gather_daily_project_context.py"
SPEC = importlib.util.spec_from_file_location("gather_daily_project_context", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class GatherDailyProjectContextTests(unittest.TestCase):
    def test_collects_matching_github_events(self):
        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-06-07T03:00:00Z",
                "repo": {"name": "wangxiao433/demo"},
                "payload": {"commits": [{"message": "fix convergence warning"}]},
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=Path(temp_dir),
                target_date=date(2026, 6, 7),
            )
            report = module.gather_daily_project_context(config, events=events)

        self.assertIn("fix convergence warning", report)
        self.assertIn("wangxiao433/demo", report)

    def test_collects_and_redacts_local_log_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            log_file = workspace / "solver.log"
            log_file.write_text(
                "ok\nerror: token=abc123 should not leak\nwarning: NaN detected\n",
                encoding="utf-8",
            )
            target_time = time.mktime((2026, 6, 7, 12, 0, 0, 0, 0, -1))
            os.utime(log_file, (target_time, target_time))

            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=workspace,
                target_date=date(2026, 6, 7),
                max_lines_per_file=10,
            )
            report = module.gather_daily_project_context(config, events=[])

        self.assertIn("solver.log", report)
        self.assertIn("token=[REDACTED]", report)
        self.assertNotIn("abc123", report)

    def test_missing_workspace_is_reported(self):
        config = module.ScanConfig(
            github_username="wangxiao433",
            workspace_path=Path("Z:/definitely/not/here"),
            target_date=date(2026, 6, 7),
        )
        report = module.gather_daily_project_context(config, events=[])

        self.assertIn("Workspace not found", report)


if __name__ == "__main__":
    unittest.main()
