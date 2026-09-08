"""选课 HTTP 客户端：会话、CSRF Token、提交和结果查询。"""

from __future__ import annotations

from collections import Counter
import datetime as dt
import json
import re
import time

import requests

from .errors import CookieError, DeadlineReached, TransientError
from .settings import DOMAIN

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CSRF_RE = re.compile(r"""id=["']csrfToken["'][^>]*value=["']([0-9a-fA-F]{32})["']""")


class Grabber:
    def __init__(self, cfg: dict, cookie: str):
        self.cfg = cfg
        self.cookie = cookie
        self.target = cfg.get("target", DOMAIN)
        self.timeout = float(cfg.get("http_timeout", 12))
        self.base = f"http://{self.target}/yjsxkapp/sys/xsxkappfudan"
        self.session = self._new_session()
        self.token: str | None = None
        self.last_homepage_ts = float("-inf")
        self.deadline: dt.datetime | None = None
        self.inflight: dict[str, str] = {}
        self.full_tries: Counter[str] = Counter()
        self.exhausted: list[dict] = []

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        for segment in self.cookie.split(";"):
            name, separator, value = segment.strip().partition("=")
            if separator and name:
                session.cookies.set(name, value, domain=self.target, path="/")
        return session

    def set_cookie(self, cookie: str) -> bool:
        changed = cookie != self.cookie
        self.cookie = cookie
        if changed:
            self.session.close()
            self.session = self._new_session()
            self.token = None
            self.last_homepage_ts = float("-inf")
        return changed

    def _headers(self) -> dict:
        return {
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def check_deadline(self) -> None:
        if self.deadline is not None and dt.datetime.now() >= self.deadline:
            raise DeadlineReached()

    def request_timeout(self) -> float:
        if self.deadline is None:
            return self.timeout
        remain = (self.deadline - dt.datetime.now()).total_seconds()
        if remain <= 0:
            raise DeadlineReached()
        return min(self.timeout, remain)

    def pause(self, seconds: float) -> None:
        if self.deadline is not None:
            seconds = min(seconds, (self.deadline - dt.datetime.now()).total_seconds())
        if seconds > 0:
            time.sleep(seconds)

    @staticmethod
    def check_response(resp: requests.Response) -> None:
        if resp.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise CookieError(f"登录态或请求权限需检查（HTTP {resp.status_code}）")
        if resp.status_code != 200:
            try:
                retry_after = max(0, float(resp.headers.get("Retry-After", "0")))
            except ValueError:
                retry_after = 0
            raise TransientError(f"服务器返回 HTTP {resp.status_code}", retry_after)

    @staticmethod
    def check_message(msg: str) -> None:
        if any(hint in msg.lower() for hint in (
            "csrftoken", "csrf token", "请重新登录", "登录超时", "登录已失效",
        )):
            raise CookieError("服务器提示登录态或 CSRF 校验失效")

    def ensure_token(self) -> str:
        interval = float(self.cfg.get("homepage_refresh_secs", 1.0))
        if self.token is None or time.monotonic() - self.last_homepage_ts >= interval:
            return self.refresh_token()
        return self.token

    def refresh_token(self) -> str:
        url = f"{self.base}/xsxkHome/gotoChooseCourse.do"
        try:
            resp = self.session.get(
                url, headers={**self._headers(), "Cache-Control": "no-cache"},
                timeout=self.request_timeout(), allow_redirects=False
            )
        except requests.RequestException as exc:
            raise TransientError(f"打开选课页网络异常：{type(exc).__name__}") from exc
        self.check_response(resp)
        m = CSRF_RE.search(resp.text)
        if not m:
            raise CookieError("页面里找不到 csrfToken，Cookie 多半已失效")
        self.token = m.group(1)
        self.last_homepage_ts = time.monotonic()
        return self.token

    def submit(self, course: dict) -> tuple[bool, str]:
        """提交选课。返回 (是否已受理, xid 或 失败原因)"""
        url = f"{self.base}/xsxkCourse/choiceCourse.do?_={int(time.time() * 1000)}"
        payload = {
            "bjdm": course["bjdm"],
            "lx": str(course["lx"]),
            "bqmc": str(course.get("bqmc", "")),
            "csrfToken": self.token,
        }
        try:
            resp = self.session.post(
                url, headers=self._headers(), data=payload,
                timeout=self.request_timeout(), allow_redirects=False
            )
        except requests.RequestException as exc:
            raise TransientError(f"提交请求网络异常：{type(exc).__name__}，本次结果未知") from exc
        self.check_response(resp)
        try:
            body = resp.json()
        except ValueError as exc:
            raise TransientError("提交响应不是 JSON，本次结果未知") from exc
        if not isinstance(body, dict) or "code" not in body:
            raise TransientError("提交响应缺少 code，本次结果未知")
        msg = body.get("msg")
        if isinstance(msg, str):
            self.check_message(msg)
        if body.get("code") == 0:
            return False, msg if isinstance(msg, str) else "被拒绝"
        if body.get("code") is None or not isinstance(msg, str) or not msg.strip():
            raise TransientError("提交响应缺少有效受理号，本次结果未知")
        return True, msg

    def probe_once(self, course: dict) -> dict:
        """向服务器发一次真实选课请求，返回原始响应 dict（演练用，不做任何重试）。"""
        url = f"{self.base}/xsxkCourse/choiceCourse.do?_={int(time.time() * 1000)}"
        payload = {
            "bjdm": course["bjdm"],
            "lx": str(course["lx"]),
            "bqmc": str(course.get("bqmc", "")),
            "csrfToken": self.token,
        }
        try:
            resp = self.session.post(
                url, headers=self._headers(), data=payload,
                timeout=self.request_timeout(), allow_redirects=False
            )
        except requests.RequestException as exc:
            return {"http": None, "code": None, "msg": f"网络异常：{type(exc).__name__}"}
        try:
            return {"http": resp.status_code, **(resp.json() or {})}
        except Exception:
            return {"http": resp.status_code, "msg": resp.text[:200], "_raw": True}

    def poll_result(self, xid: str) -> tuple[int | None, str]:
        """轮询选课结果。返回 (code, 说明)；code==1 表示真的选上了。"""
        max_times = int(self.cfg.get("poll_max", 30))
        interval = float(self.cfg.get("poll_interval", 0.6))
        last_network_error: str | None = None
        for _ in range(max_times):
            url = f"{self.base}/xsxkCourse/loadXkjgRes.do?_={int(time.time() * 1000)}"
            try:
                resp = self.session.post(
                    url,
                    headers=self._headers(),
                    data={"xid": xid, "sfhqdqxkqqs": 0},
                    timeout=self.request_timeout(),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                last_network_error = type(exc).__name__
                retry_delay = min(12, max(interval, 1) * 2 ** min(_, 4))
                self.pause(retry_delay)
                continue
            self.check_response(resp)
            try:
                body = resp.json()
            except ValueError:
                return None, f"轮询响应不是 JSON（HTTP {resp.status_code}）"
            if not isinstance(body, dict):
                return None, "轮询响应格式异常"
            msg = body.get("msg")
            if msg:
                if isinstance(msg, str):
                    self.check_message(msg)
                try:
                    detail = json.loads(msg) if isinstance(msg, str) else msg
                except ValueError:
                    return None, str(msg)
                if not isinstance(detail, dict) or detail.get("code") not in (0, 1):
                    return None, "轮询尚未返回明确结果"
                return detail["code"], str(detail.get("msg") or "")
            self.pause(interval)
        if last_network_error:
            return None, f"轮询网络异常：{last_network_error}（请去「已选课程」页确认）"
        return None, "轮询超时，结果未知（请去「已选课程」页确认）"
