"""仅向本机提供课程页面和JSON，不提供目录或其他项目文件。"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import webbrowser

from .settings import BASE_DIR


def handler_for(root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Host") not in (
                f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
            ):
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            }
            if path in assets:
                filename, content_type = assets[path]
                file = root / "web" / "catalog" / filename
            elif path == "/api/courses":
                file = root / "exports" / "course-list.json"
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            try:
                payload = file.read_bytes()
                if path == "/api/courses":
                    data = json.loads(payload)
                    if not isinstance(data, dict) or not isinstance(data.get("courses"), list):
                        raise ValueError("invalid catalog")
            except FileNotFoundError:
                self.send_error(404)
                return
            except (OSError, ValueError):
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            pass
    return Handler


def main() -> None:
    # 系统分配空闲端口，避免误连接其他已占用端口的服务。
    with ThreadingHTTPServer(("127.0.0.1", 0), handler_for(Path(BASE_DIR))) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"课程浏览页：{url}\n等待 exports/course-list.json；采集后自动更新。Ctrl+C 关闭。", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("课程浏览服务已停止。")


if __name__ == "__main__":
    main()
