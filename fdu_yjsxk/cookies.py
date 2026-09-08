"""读取指定选课域名的浏览器 Cookie，按配置回退到 cookie.txt。"""

from __future__ import annotations

import glob
import os
import sys

from .errors import CookieError
from .logging import log
from .settings import COOKIE_PATH, DOMAIN


def cookie_from_browser(browser: str = "edge", domain: str = DOMAIN):
    """从浏览器本地 Cookie 库读取指定选课域名的 Cookie。"""
    try:
        import browser_cookie3
    except ImportError:
        return None, "browser-cookie3 未安装（请运行 uv sync --locked）"

    getter = {"edge": "edge", "chrome": "chrome"}.get(browser)
    if not getter or not hasattr(browser_cookie3, getter):
        return None, f"不支持的浏览器：{browser}"

    cookie_files: list[str | None] = [None]
    if sys.platform == "darwin" and browser == "edge":
        app_support = os.path.expanduser("~/Library/Application Support")
        for channel in ("Microsoft Edge", "Microsoft Edge Beta", "Microsoft Edge Dev", "Microsoft Edge Canary"):
            root = os.path.join(app_support, channel)
            for pattern in (
                os.path.join(root, "Default", "Network", "Cookies"),
                os.path.join(root, "Profile *", "Network", "Cookies"),
                os.path.join(root, "Default", "Cookies"),
                os.path.join(root, "Profile *", "Cookies"),
            ):
                cookie_files.extend(glob.glob(pattern))

    errors: list[str] = []
    seen_files: set[str | None] = set()
    for cookie_file in cookie_files:
        if cookie_file in seen_files:
            continue
        seen_files.add(cookie_file)
        kwargs = {"domain_name": domain}
        if cookie_file:
            kwargs["cookie_file"] = cookie_file
        try:
            jar = getattr(browser_cookie3, getter)(**kwargs)
        except Exception as exc:  # 权限、钥匙串、数据库锁等
            errors.append(str(exc))
            continue

        picked: dict[str, str] = {}
        for c in jar:
            d = (c.domain or "").lstrip(".")
            if d and (domain == d or domain.endswith("." + d)):
                picked[c.name.strip()] = c.value.strip()
        if picked:
            return "; ".join(f"{name}={value}" for name, value in picked.items()), None

    if errors and all("Unable to read database file" in error for error in errors):
        return None, (
            "读取浏览器 Cookie 失败：Unable to read database file。请在 macOS「系统设置 → "
            "隐私与安全性 → 完全磁盘访问权限」中允许终端，然后彻底退出并重新打开终端"
        )
    return None, f"浏览器里没有 {domain} 的 Cookie（请先在 Edge 登录该选课域名）"


def cookie_from_file():
    if not os.path.exists(COOKIE_PATH):
        return None, "cookie.txt 不存在"
    try:
        with open(COOKIE_PATH, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return None, f"读取 cookie.txt 失败：{exc}"
    raw = " ".join(raw.split())
    if not raw or raw.startswith("#"):
        return None, "cookie.txt 为空"
    return raw, None


def obtain_cookie(cfg: dict) -> str:
    """按 cookie_source 取 Cookie：auto / browser / file。"""
    source = cfg.get("cookie_source", "auto")
    browser = cfg.get("browser", "edge")
    target = cfg.get("target", DOMAIN)

    if source in ("auto", "browser"):
        value, err = cookie_from_browser(browser, target)
        if value:
            return value
        log(f"  浏览器取 Cookie 未成功：{err}")
        if source == "browser":
            raise CookieError(err)

    value, err = cookie_from_file()
    if value:
        return value
    raise CookieError(
        f"{err}。请先在 Edge/Chrome 登录 http://{target} ，"
        f"或把 Cookie 粘贴进 {os.path.basename(COOKIE_PATH)}"
    )
