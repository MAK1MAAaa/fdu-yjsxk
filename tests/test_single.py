from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from fdu_yjsxk import cli, single


class SingleCourseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = {
            "start_time": "2026-09-01 12:59:56",
            "end_time": "2026-09-01 15:00:00",
            "serial_mode": True,
            "request_interval": 0.8,
            "round_interval": 0,
            "full_max_tries": 3,
            "cookie_refresh_secs": 240,
            "courses": [
                {"name": "课程甲", "bjdm": "A", "lx": "7", "enabled": True},
                {"name": "停用课程", "bjdm": "B", "lx": "7", "enabled": False},
                {"name": "已选课程", "bjdm": "C", "lx": "7", "selected": True},
                {"name": "课程乙", "bjdm": "D", "lx": "8"},
            ],
        }
        self.before = deepcopy(self.cfg)
        patcher = patch("requests.sessions.Session.request", side_effect=AssertionError("禁止真实请求"))
        patcher.start()
        self.addCleanup(patcher.stop)
        log_patcher = patch.object(single, "log")
        self.logger = log_patcher.start()
        self.addCleanup(log_patcher.stop)

    def test_menu_filters_disabled_and_selected_courses_without_reordering(self) -> None:
        self.assertEqual([c["bjdm"] for c in single.available_courses(self.cfg)], ["A", "D"])
        self.assertEqual(self.cfg, self.before)

    def test_single_config_uses_fresh_window_and_does_not_mutate_original(self) -> None:
        result = single.build_single_config(
            self.cfg, self.cfg["courses"][3], 120, datetime(2026, 9, 8, 18),
        )
        self.assertEqual(result["start_time"], "2026-09-08 18:00:00")
        self.assertEqual(result["end_time"], "2026-09-08 20:00:00")
        self.assertEqual([c["bjdm"] for c in result["courses"]], ["D"])
        self.assertEqual(result["full_max_tries"], 0)
        self.assertEqual(result["request_interval"], 0.8)
        self.assertEqual(result["cookie_refresh_secs"], 240)
        result["courses"][0]["name"] = "only in memory"
        self.assertEqual(self.cfg, self.before)

    def test_menu_selects_exactly_one_course_and_defaults_to_two_hours(self) -> None:
        with patch("builtins.input", side_effect=["2", ""]), patch("builtins.print"):
            with patch.object(single, "run", return_value=1) as run:
                self.assertEqual(single.run_single(self.cfg), 1)
        run.assert_called_once()
        args, kwargs = run.call_args
        session = args[0]
        self.assertEqual([c["bjdm"] for c in session["courses"]], ["D"])
        self.assertEqual(kwargs, {"start_now": True})
        start = datetime.fromisoformat(session["start_time"])
        end = datetime.fromisoformat(session["end_time"])
        self.assertEqual((end - start).total_seconds(), 7200)
        self.assertEqual(self.cfg, self.before)

    def test_custom_duration_can_cross_midnight(self) -> None:
        result = single.build_single_config(
            self.cfg, self.cfg["courses"][0], 60, datetime(2026, 9, 8, 23, 30),
        )
        self.assertEqual(result["end_time"], "2026-09-09 00:30:00")

    def test_success_reports_target_and_stops_after_one_run(self) -> None:
        with patch("builtins.input", side_effect=["2", "1"]), patch("builtins.print"):
            with patch.object(single, "run", return_value=0) as run:
                self.assertEqual(single.run_single(self.cfg), 0)
        run.assert_called_once()
        messages = "\n".join(call.args[0] for call in self.logger.call_args_list)
        self.assertIn("目标课程：课程乙（D）", messages)
        self.assertIn("已自动停止", messages)
        self.assertIn("结束时间", messages)
        self.assertIn("本次耗时", messages)

    def test_failure_report_does_not_claim_success(self) -> None:
        with patch("builtins.input", side_effect=["1", "1"]), patch("builtins.print"):
            with patch.object(single, "run", return_value=1):
                self.assertEqual(single.run_single(self.cfg), 1)
        messages = "\n".join(call.args[0] for call in self.logger.call_args_list)
        self.assertIn("不计为成功", messages)
        self.assertNotIn("结果：目标已选上", messages)

    def test_invalid_number_and_multiple_choices_are_reprompted(self) -> None:
        with patch("builtins.input", side_effect=["", "1,2", "-1", "9", "2"]):
            with patch("builtins.print"):
                self.assertEqual(single.read_number("选择：", 2), 2)

    def test_cancel_or_eof_never_enters_enrollment_loop(self) -> None:
        for answers in (["0"], ["1", "0"], [EOFError()], ["1", EOFError()]):
            with self.subTest(answers=answers):
                with patch("builtins.input", side_effect=answers), patch("builtins.print"):
                    with patch.object(single, "run") as run:
                        self.assertEqual(single.run_single(self.cfg), 0)
                        run.assert_not_called()

    def test_empty_list_does_not_prompt_or_enter_enrollment_loop(self) -> None:
        self.cfg["courses"] = []
        with patch("builtins.input") as prompt, patch("builtins.print"):
            with patch.object(single, "run") as run:
                self.assertEqual(single.run_single(self.cfg), 0)
                prompt.assert_not_called()
                run.assert_not_called()

    def test_invalid_duration_is_rejected(self) -> None:
        for minutes in (0, -1, 1441):
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                single.build_single_config(self.cfg, self.cfg["courses"][0], minutes, datetime.now())

    def test_single_cli_dispatch(self) -> None:
        with patch.object(sys, "argv", ["grab.py", "--single"]):
            with patch.object(cli, "load_config", return_value=self.cfg):
                with patch.object(cli, "run_single", return_value=0) as run_single:
                    with patch.object(cli, "run") as regular:
                        self.assertEqual(cli.main(), 0)
                        run_single.assert_called_once_with(self.cfg)
                        regular.assert_not_called()

    def test_conflicting_flags_fail_before_loading_config(self) -> None:
        for flag in ("--dry-run", "--probe", "--force", "--now"):
            with self.subTest(flag=flag):
                with patch.object(sys, "argv", ["grab.py", "--single", flag]):
                    with patch.object(cli, "load_config") as load, patch("sys.stderr"):
                        with self.assertRaises(SystemExit) as error:
                            cli.main()
                        self.assertEqual(error.exception.code, 2)
                        load.assert_not_called()

    def test_real_cli_help_from_foreign_directory(self) -> None:
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-B", str(root / "grab.py"), "--help"],
            cwd=root.parent, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--single", result.stdout)


if __name__ == "__main__":
    unittest.main()
