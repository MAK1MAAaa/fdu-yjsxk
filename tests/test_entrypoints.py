from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fdu_yjsxk import cli, settings


ROOT = Path(__file__).resolve().parent.parent


class EntrypointTests(unittest.TestCase):
    def test_launchers_resolve_project_parent(self) -> None:
        for name in ("一键抢课", "单课程捡漏", "先跑自检"):
            with self.subTest(name=name):
                mac = ROOT / "scripts" / f"{name}.command"
                windows = ROOT / "scripts" / f"{name}.bat"
                self.assertIn('cd "${0:A:h}/.." || exit 1', mac.read_text())
                self.assertIn('cd /d "%~dp0.."', windows.read_text())
                self.assertIn('if errorlevel 1 exit /b 1', windows.read_text())
                self.assertFalse((ROOT / mac.name).exists())
                self.assertFalse((ROOT / windows.name).exists())

    def test_old_entrypoint_works_from_another_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-B", str(ROOT / "grab.py"), "--help"],
                cwd=directory, capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--probe", result.stdout)

    def test_package_entrypoint_supports_existing_arguments(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "fdu_yjsxk", "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--now", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_runtime_paths_still_point_to_project_root(self) -> None:
        self.assertEqual(Path(settings.BASE_DIR), ROOT)
        for path in (settings.CONFIG_PATH, settings.COOKIE_PATH, settings.LOG_PATH):
            self.assertEqual(Path(path).parent, ROOT)

    def test_parallel_config_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "仅支持串行"):
            settings.validate_config({"serial_mode": False})

    def test_dry_run_dispatch_does_not_enter_enrollment_loop(self) -> None:
        cfg = {"test": "configuration"}
        with patch.object(cli, "load_config", return_value=cfg):
            with patch.object(cli, "dry_run", return_value=0) as check:
                with patch.object(cli, "run") as run:
                    with patch.object(sys, "argv", ["grab.py", "--dry-run"]):
                        self.assertEqual(cli.main(), 0)
        check.assert_called_once_with(cfg)
        run.assert_not_called()

    def test_keyboard_interrupt_and_validation_exit_codes_are_preserved(self) -> None:
        for error, expected in ((KeyboardInterrupt(), 130), (ValueError("invalid"), 1)):
            with self.subTest(expected=expected):
                with patch.object(cli, "main", side_effect=error):
                    with patch.object(cli, "log"):
                        with self.assertRaises(SystemExit) as raised:
                            cli.entrypoint()
                self.assertEqual(raised.exception.code, expected)

    def test_interactive_interval_preserves_schedule_and_original_config(self) -> None:
        cfg = {
            "request_interval": 0.8, "start_time": "2026-09-09 12:59:56",
            "end_time": "2026-09-09 15:00:00", "homepage_refresh_secs": 60,
            "courses": [{"name": "first"}, {"name": "second"}],
        }
        before = deepcopy(cfg)
        for answer, expected in (("0.1", 0.1), ("", 0.8)):
            with self.subTest(answer=answer):
                with patch.object(sys, "argv", ["grab.py", "--ask-interval"]):
                    with patch.object(cli, "load_config", return_value=cfg):
                        with patch("builtins.input", return_value=answer), patch("builtins.print"):
                            with patch.object(cli, "run", return_value=1) as run:
                                self.assertEqual(cli.main(), 1)
                session = run.call_args.args[0]
                self.assertEqual(session, {**before, "request_interval": expected})
                self.assertEqual(run.call_args.kwargs, {"start_now": False})
                self.assertIsNot(session["courses"], cfg["courses"])
                self.assertEqual(cfg, before)

    def test_interval_cancel_never_starts_run(self) -> None:
        for answer in ("0", EOFError()):
            with self.subTest(answer=answer):
                with patch.object(sys, "argv", ["grab.py", "--ask-interval"]):
                    with patch.object(cli, "load_config", return_value={"request_interval": 0.8}):
                        with patch("builtins.input", side_effect=[answer]), patch("builtins.print"):
                            with patch.object(cli, "run") as run:
                                self.assertEqual(cli.main(), 0)
                                run.assert_not_called()

    def test_interval_conflicts_are_rejected_before_config_read(self) -> None:
        for flag in ("--single", "--dry-run", "--probe", "--force"):
            with self.subTest(flag=flag):
                with patch.object(sys, "argv", ["grab.py", "--ask-interval", flag]):
                    with patch.object(cli, "load_config") as load, patch("sys.stderr"):
                        with self.assertRaises(SystemExit) as error:
                            cli.main()
                        self.assertEqual(error.exception.code, 2)
                        load.assert_not_called()

    def test_original_cli_does_not_prompt_for_interval(self) -> None:
        cfg = {"request_interval": 0.8}
        with patch.object(sys, "argv", ["grab.py"]):
            with patch.object(cli, "load_config", return_value=cfg):
                with patch("builtins.input") as prompt, patch.object(cli, "run", return_value=0) as run:
                    self.assertEqual(cli.main(), 0)
                    prompt.assert_not_called()
                    run.assert_called_once_with(cfg, start_now=False)


if __name__ == "__main__":
    unittest.main()
