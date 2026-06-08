import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gather_daily_project_context.py"
SPEC = importlib.util.spec_from_file_location("gather_daily_project_context", SCRIPT_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def set_local_mtime(path: Path, year: int, month: int, day: int, hour: int = 12) -> None:
    stamp = datetime(year, month, day, hour, tzinfo=timezone(timedelta(hours=8))).timestamp()
    os.utime(path, (stamp, stamp))


class GatherDailyProjectContextTests(unittest.TestCase):
    def test_collects_matching_github_events_in_weekly_window(self):
        events = [
            {
                "type": "PushEvent",
                "created_at": "2026-06-01T03:00:00Z",
                "repo": {"name": "wangxiao433/demo"},
                "payload": {"commits": [{"message": "fix convergence warning", "sha": "abc123"}]},
            },
            {
                "type": "PushEvent",
                "created_at": "2026-05-20T03:00:00Z",
                "repo": {"name": "wangxiao433/old"},
                "payload": {"commits": [{"message": "old work"}]},
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=Path(temp_dir),
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
            )
            report = module.build_report(config, events=events)

        rendered = module.render_markdown(report)
        self.assertIn("fix convergence warning", rendered)
        self.assertIn("wangxiao433/demo", rendered)
        self.assertNotIn("old work", rendered)

    def test_collects_and_redacts_local_log_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            log_file = workspace / "solver.log"
            log_file.write_text(
                "ok\nerror: token=abc123 should not leak\nwarning: NaN detected\n",
                encoding="utf-8",
            )
            set_local_mtime(log_file, 2026, 6, 7)

            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=workspace,
                start_date=date(2026, 6, 7),
                end_date=date(2026, 6, 7),
                max_lines_per_file=10,
            )
            report = module.build_report(config, events=[])

        rendered = module.render_markdown(report)
        self.assertIn("solver.log", rendered)
        self.assertIn("token=[REDACTED]", rendered)
        self.assertNotIn("abc123", rendered)
        self.assertIn("nan", json.dumps(report, ensure_ascii=False).lower())
        self.assertIn("中文复盘草稿", rendered)
        self.assertNotIn("\u6d93", rendered)

    def test_engineering_log_parsers_detect_ansys_zemax_and_mujoco(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            ansys_log = workspace / "ansys_solver.out"
            zemax_log = workspace / "opticstudio_trace.log"
            mujoco_log = workspace / "mujoco_run.err"
            ansys_log.write_text(
                "ANSYS Mechanical Solver\nFATAL ERROR: convergence not achieved due to negative volume\n",
                encoding="utf-8",
            )
            zemax_log.write_text(
                "Zemax OpticStudio\nRay trace error: no intersection at surface 4\n",
                encoding="utf-8",
            )
            mujoco_log.write_text(
                "MuJoCo warning\nNan detected in qpos and qvel; constraint solver unstable\n",
                encoding="utf-8",
            )
            for path in (ansys_log, zemax_log, mujoco_log):
                set_local_mtime(path, 2026, 6, 7)

            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=workspace,
                start_date=date(2026, 6, 7),
                end_date=date(2026, 6, 7),
                max_lines_per_file=10,
            )
            report = module.build_report(config, events=[])

        logs_by_path = {record["path"]: record for record in report["local_logs"]}
        self.assertIn("Ansys", logs_by_path["ansys_solver.out"]["detected_tools"])
        self.assertIn("Zemax/OpticStudio", logs_by_path["opticstudio_trace.log"]["detected_tools"])
        self.assertIn("MuJoCo", logs_by_path["mujoco_run.err"]["detected_tools"])
        self.assertEqual(logs_by_path["ansys_solver.out"]["highest_severity"], "critical")
        self.assertEqual(logs_by_path["opticstudio_trace.log"]["highest_severity"], "critical")
        self.assertEqual(logs_by_path["mujoco_run.err"]["highest_severity"], "critical")
        rendered = module.render_markdown(report)
        self.assertIn("detected_tools", json.dumps(report, ensure_ascii=False))
        self.assertIn("Ansys", rendered)
        self.assertIn("Zemax/OpticStudio", rendered)
        self.assertIn("MuJoCo", rendered)

    def test_json_output_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = module.ScanConfig(
                github_username="wangxiao433",
                workspace_path=Path(temp_dir),
                start_date=date(2026, 6, 7),
                end_date=date(2026, 6, 7),
                output_format="json",
            )
            report = module.build_report(config, events=[])

        rendered = module.render_report(report, "json")
        parsed = json.loads(rendered)
        self.assertEqual(parsed["scope"]["github_username"], "wangxiao433")
        self.assertIn("github_activity", parsed)
        self.assertIn("local_logs", parsed)
        self.assertNotIn("", parsed["review"]["missing_context"])

    def test_simple_yaml_config_is_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            config_file = Path(temp_dir) / "config.yaml"
            config_file.write_text(
                "\n".join(
                    [
                        "github_username: wangxiao433",
                        f"workspace_path: {workspace}",
                        "since: 2026-06-01",
                        "until: 2026-06-07",
                        "repositories:",
                        "  - wangxiao433/My-Agent-Skills",
                        "keywords: [error, residual]",
                        "log_tools: [ansys, mujoco]",
                        "include_ci: false",
                        "include_pr_details: false",
                        f"cache_dir: {Path(temp_dir) / 'cache'}",
                        "cache_ttl_seconds: 3600",
                        "max_files: 5",
                    ]
                ),
                encoding="utf-8",
            )

            args = module.parse_args(["--config", str(config_file), "--format", "json"])
            config = module.build_config(args)

        self.assertEqual(config.github_username, "wangxiao433")
        self.assertEqual(config.start_date, date(2026, 6, 1))
        self.assertEqual(config.end_date, date(2026, 6, 7))
        self.assertEqual(config.repositories, ("wangxiao433/My-Agent-Skills",))
        self.assertIn("residual", config.keywords)
        self.assertEqual(config.log_tools, ("ansys", "mujoco"))
        self.assertFalse(config.include_ci)
        self.assertFalse(config.include_pr_details)
        self.assertEqual(config.cache_ttl_seconds, 3600)

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            output = Path(temp_dir) / "review.md"
            exit_code = module.main(
                [
                    "--github-username",
                    "wangxiao433",
                    "--workspace-path",
                    str(workspace),
                    "--date",
                    "2026-06-07",
                    "--format",
                    "markdown",
                    "--output",
                    str(output),
                    "--no-public-events",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            self.assertIn("Project Context Review", output.read_text(encoding="utf-8"))

    def test_missing_workspace_is_reported(self):
        config = module.ScanConfig(
            github_username="wangxiao433",
            workspace_path=Path("Z:/definitely/not/here"),
            start_date=date(2026, 6, 7),
            end_date=date(2026, 6, 7),
        )
        report = module.build_report(config, events=[])

        self.assertIn("Workspace not found", report["errors"][0])


if __name__ == "__main__":
    unittest.main()
