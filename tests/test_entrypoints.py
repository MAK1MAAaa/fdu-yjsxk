from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fdu_yjsxk import cli, settings


ROOT = Path(__file__).resolve().parent.parent


class EntrypointTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
