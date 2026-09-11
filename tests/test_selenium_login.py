from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fdu_yjsxk.selenium_login import cookie_header, save_cookie, fill_login_form


class SeleniumCookieTests(unittest.TestCase):
    def test_form_fill_is_verified_without_submission(self):
        user, password, button = Mock(), Mock(), Mock()
        button.text = "登录"
        user.get_attribute.return_value = "test-user"
        password.get_attribute.return_value = "test-password"
        driver = Mock(current_url="https://id.fudan.edu.cn/ac/")
        driver.find_elements.side_effect = [[user], [password], [button]]
        self.assertIs(fill_login_form(driver, "test-user", "test-password"), button)
        user.send_keys.assert_called_once_with("test-user")
        password.send_keys.assert_called_once_with("test-password")
        button.click.assert_not_called()

    def test_untrusted_origin_never_receives_credentials(self):
        for url in ("http://id.fudan.edu.cn/", "https://id.fudan.edu.cn.evil.test/"):
            driver = Mock(current_url=url)
            self.assertIsNone(fill_login_form(driver, "user", "password"))
            driver.find_elements.assert_not_called()

    def test_unready_form_is_not_filled(self):
        driver = Mock(current_url="https://id.fudan.edu.cn/ac/")
        user, password = Mock(), Mock()
        driver.find_elements.side_effect = [[user], [password], []]
        self.assertIsNone(fill_login_form(driver, "user", "password"))
        user.send_keys.assert_not_called()

    def test_failed_fill_is_not_ready_for_submission(self):
        user, password, button = Mock(), Mock(), Mock()
        button.text = "登录"
        user.get_attribute.return_value = ""
        driver = Mock(current_url="https://id.fudan.edu.cn/ac/")
        driver.find_elements.side_effect = [[user], [password], [button]]
        self.assertIsNone(fill_login_form(driver, "user", "password"))
        button.click.assert_not_called()

    def test_disabled_button_does_not_block_filling(self):
        user, password, button = Mock(), Mock(), Mock()
        button.text = "登录"
        button.is_enabled.return_value = False
        user.get_attribute.return_value = "user"
        password.get_attribute.return_value = "password"
        driver = Mock(current_url="https://id.fudan.edu.cn/ac/")
        driver.find_elements.side_effect = [[user], [password], [button]]
        self.assertIsNone(fill_login_form(driver, "user", "password"))
        user.send_keys.assert_called_once_with("user")
        password.send_keys.assert_called_once_with("password")
        button.click.assert_not_called()

    def test_cookie_domains_are_filtered(self):
        items = [
            {"domain": "yjsxk.fudan.sh.cn", "name": "JSESSIONID", "value": "test"},
            {"domain": "id.fudan.edu.cn", "name": "sso", "value": "private"},
            {"domain": "evilyjsxk.fudan.sh.cn", "name": "bad", "value": "bad"},
        ]
        self.assertEqual(cookie_header(items, "yjsxk.fudan.sh.cn"), "JSESSIONID=test")

    def test_missing_session_is_rejected(self):
        with self.assertRaises(ValueError):
            cookie_header([], "yjsxk.fudan.sh.cn")

    def test_cookie_saved_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.txt"
            save_cookie("JSESSIONID=test", path)
            self.assertEqual(path.read_text(), "JSESSIONID=test\n")
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_replace_preserves_previous_cookie(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookie.txt"
            save_cookie("old", path)
            with patch("fdu_yjsxk.selenium_login.os.replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    save_cookie("new", path)
            self.assertEqual(path.read_text(), "old\n")
            self.assertEqual(list(Path(directory).iterdir()), [path])
