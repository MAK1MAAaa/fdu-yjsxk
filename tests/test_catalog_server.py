import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fdu_yjsxk.catalog_server import handler_for
from fdu_yjsxk.course_catalog import write_json_atomic


class CatalogServerTests(unittest.TestCase):
    def request(self, root, path, host="127.0.0.1:1234"):
        request = Mock(path=path, headers={"Host": host}, wfile=io.BytesIO())
        request.server.server_port = 1234
        handler_for(root).do_GET(request)
        return request

    def test_missing_then_created_file_is_read_on_each_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.request(root, "/api/courses").send_error.assert_called_once_with(404)
            (root / "exports").mkdir()
            write_json_atomic(root / "exports/course-list.json", {"courses": []})
            response = self.request(root, "/api/courses")
            response.send_response.assert_called_once_with(200)
            self.assertEqual(json.loads(response.wfile.getvalue()), {"courses": []})

    def test_private_files_and_foreign_hosts_are_not_served(self):
        for path in ("/.env", "/cookie.txt", "/config.json", "/../config.json"):
            self.request(Path("/unused"), path).send_error.assert_called_once_with(404)
        self.request(Path("/unused"), "/", "example.com:1234").send_error.assert_called_once_with(403)

    def test_invalid_catalog_returns_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "exports").mkdir()
            write_json_atomic(root / "exports/course-list.json", {"wrong": []})
            self.request(root, "/api/courses").send_error.assert_called_once_with(503)

    def test_only_named_assets_are_served(self):
        root = Path(__file__).resolve().parent.parent
        for path, mime in (("/", "text/html"), ("/styles.css", "text/css"), ("/app.js", "text/javascript")):
            response = self.request(root, path)
            response.send_response.assert_called_once_with(200)
            response.send_header.assert_any_call("Content-Type", mime + "; charset=utf-8")
        self.request(root, "/web/catalog/../../.env").send_error.assert_called_once_with(404)
