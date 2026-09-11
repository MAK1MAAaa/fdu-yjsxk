from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from fdu_yjsxk import course_catalog as catalog


class CourseCatalogTests(unittest.TestCase):
    def test_two_level_tabs_are_used_and_no_enrollment_button_is_clicked(self):
        driver = Mock()
        driver.find_element.return_value.is_displayed.return_value = True
        driver.find_element.return_value.is_enabled.return_value = True
        row = {"cells": ["课程2026202701GEIP40015.13"]}
        driver.execute_script.side_effect = [item for _ in range(6) for item in (True, [row])]
        with patch.object(catalog.time, "sleep"), patch("builtins.print"):
            result = catalog.collect(driver)
        selectors = [call.args[1] for call in driver.find_element.call_args_list]
        self.assertEqual(selectors, ["#xkkctab_7", "#ggkc_tab_container li[tabwid='1']",
            "#ggkc_tab_container li[tabwid='2']", "#ggkc_tab_container li[tabwid='3']",
            "#xkkctab_8", "#xwzyk_tab_container li[tabwid='4']",
            "#xwzyk_tab_container li[tabwid='5']", "#xwzyk_tab_container li[tabwid='6']"])
        self.assertEqual(len(result["courses"]), 6)
        self.assertEqual(result["unresolved"], [])
        self.assertTrue(all(not c["enabled"] for c in result["courses"]))

    def test_full_class_without_enrollment_button_is_parsed(self):
        rows = [{"cells": ["学位基础课", "EIE50009", "高级软件开发技术2026202701EIE50009.01",
                           "36", "2", "张天戈", "江湾校区", "星期五 11~12节", "已满"], "code": ""}]
        courses, unresolved = catalog.parse_rows(rows)
        self.assertEqual(unresolved, [])
        self.assertEqual(courses[0]["bjdm"], "2026202701EIE50009.01")
        self.assertEqual(courses[0]["name"], "高级软件开发技术")
        self.assertEqual((courses[0]["lx"], courses[0]["bqmc"]), ("8", "4"))
        self.assertFalse(courses[0]["enabled"])

    def test_unknown_category_is_not_guessed(self):
        valid, unknown = catalog.parse_rows([{"cells": ["课程2026202701GEIP40015.13"]}])
        self.assertEqual(valid, [])
        self.assertNotIn("lx", unknown[0])

    def test_export_uses_dedicated_json_without_touching_config(self):
        data = {"courses": [{"name": "测试", "enabled": False}], "unresolved": [], "notes": []}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(catalog, "BASE_DIR", directory), patch.object(catalog, "collect", return_value=data):
                with patch("builtins.print"):
                    path = catalog.export_catalog(object())
            self.assertEqual(path, Path(directory) / "exports" / "course-list.json")
            self.assertEqual(json.loads(path.read_text()), data)
            self.assertFalse((Path(directory) / "config.json").exists())

    def test_failed_atomic_update_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "course-list.json"
            catalog.write_json_atomic(path, {"old": True})
            with patch.object(catalog.os, "replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    catalog.write_json_atomic(path, {"new": True})
            self.assertEqual(json.loads(path.read_text()), {"old": True})
