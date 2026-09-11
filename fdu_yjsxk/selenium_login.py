"""显式启动浏览器登录，验证后原子保存 Cookie；不提交选课。"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlparse
from typing import Any

from .client import Grabber
from .settings import BASE_DIR, COOKIE_PATH, load_config


def cookie_header(items: list[dict], target: str) -> str:
    picked = {}
    for item in items:
        domain = item.get("domain", "").lstrip(".")
        if domain and (target == domain or target.endswith("." + domain)):
            name, value = item["name"], item["value"]
            if any(c in name + value for c in "\r\n;"):
                raise ValueError("Cookie 包含非法字符")
            picked[name] = value
    if not picked.get("JSESSIONID"):
        raise ValueError("未取得选课会话 Cookie")
    return "; ".join(f"{key}={value}" for key, value in picked.items())


def save_cookie(value: str, path: Path = Path(COOKIE_PATH)) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".cookie-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fill_login_form(driver: Any, username: str, password: str) -> Any | None:
    """匹配当前认证表单，填写但不提交；未就绪时交给等待循环重试。"""
    location = urlparse(driver.current_url)
    if location.scheme != "https" or location.hostname != "id.fudan.edu.cn":
        return None
    users = driver.find_elements("css selector", "#login-username")
    passwords = driver.find_elements("css selector", "#login-password")
    buttons = driver.find_elements("css selector", "button")
    user = next((e for e in users if e.is_displayed() and e.is_enabled()), None)
    secret = next((e for e in passwords if e.is_displayed() and e.is_enabled()), None)
    submit = [e for e in buttons if e.is_displayed() and e.text.strip() == "登录"]
    if user is None or secret is None or len(submit) != 1:
        return None
    user.clear()
    user.send_keys(username)
    secret.clear()
    secret.send_keys(password)
    if user.get_attribute("value") != username or secret.get_attribute("value") != password:
        return None
    return submit[0] if submit[0].is_enabled() else None


def login(cfg: dict, wait_seconds: float = 180, on_authenticated=None) -> str:
    from dotenv import load_dotenv
    from selenium import webdriver
    from selenium.common.exceptions import (
        ElementNotInteractableException, NoSuchElementException,
        StaleElementReferenceException, TimeoutException,
    )
    from selenium.webdriver.common.by import By

    target = cfg.get("target", "yjsxk.fudan.edu.cn")
    if target not in ("yjsxk.fudan.sh.cn", "yjsxk.fudan.edu.cn"):
        raise ValueError("自动登录仅支持复旦选课域名")
    browser = cfg.get("browser", "edge")
    if browser not in ("edge", "chrome"):
        raise ValueError("自动登录仅支持 Edge / Chrome")
    load_dotenv(Path(BASE_DIR) / ".env", override=False)
    username, password = os.getenv("FDU_USERNAME"), os.getenv("FDU_PASSWORD")
    print("凭据已加载，将尝试自动填写。" if username and password else
          "未加载到完整 FDU_USERNAME / FDU_PASSWORD，请在浏览器手动登录。", flush=True)
    print(f"正在启动 {browser}，首次运行可能需要下载驱动。", flush=True)
    options = webdriver.EdgeOptions() if browser == "edge" else webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    driver = webdriver.Edge(options=options) if browser == "edge" else webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(30)
        try:
            driver.get(f"http://{target}/yjsxkapp/sys/xsxkappfudan/xsxkHome/gotoChooseCourse.do")
        except TimeoutException:
            print("页面资源加载超时，继续检查已显示的登录表单。", flush=True)
        print(f"正在等待表单。验证码或二次验证请手动完成；最多等待 {wait_seconds:g} 秒。", flush=True)
        deadline = time.monotonic() + wait_seconds
        attempted = False
        last_host = None
        next_status = time.monotonic() + 10
        while time.monotonic() < deadline:
            location = urlparse(driver.current_url)
            if location.hostname != last_host:
                last_host = location.hostname
                print(f"当前域名：{last_host}（不输出认证链接参数）", flush=True)
            if time.monotonic() >= next_status:
                print("等待认证跳转或人工验证。" if attempted else "等待可填写的账号密码表单。", flush=True)
                next_status = time.monotonic() + 15
            if location.hostname == target:
                tokens = driver.find_elements(By.CSS_SELECTOR, "#csrfToken")
                if tokens and tokens[0].get_attribute("value"):
                    value = cookie_header(driver.get_cookies(), target)
                    client = Grabber(cfg, value)
                    try:
                        client.refresh_token()
                        value = cookie_header([
                            {"name": c.name, "value": c.value, "domain": c.domain}
                            for c in client.session.cookies
                        ], target)
                        if on_authenticated is not None:
                            try:
                                on_authenticated(driver)
                            except Exception as exc:
                                print(f"课程导出未完成（{type(exc).__name__}），仍保存已验证的 Cookie。请核对页面后重试。")
                        return value
                    finally:
                        client.session.close()
            if (not attempted and username and password and location.scheme == "https"
                    and location.hostname == "id.fudan.edu.cn"):
                try:
                    button = fill_login_form(driver, username, password)
                    if button is not None:
                        print("账号密码已填写并校验，正在点击登录。", flush=True)
                        attempted = True
                        button.click()
                        print("已点击登录一次；验证码或登录失败请在浏览器处理，不自动重复提交。", flush=True)
                except (NoSuchElementException, StaleElementReferenceException, ElementNotInteractableException):
                    if attempted:
                        print("点击登录时页面发生变化，请手动核对；不自动再次提交。", flush=True)
            time.sleep(0.5)
        raise ValueError("等待登录超时，旧 cookie.txt 未覆盖")
    finally:
        driver.quit()


def main() -> int:
    import argparse
    from .course_catalog import export_catalog

    parser = argparse.ArgumentParser(description="登录并可选导出课程列表，不提交选课")
    parser.add_argument("--export-courses", action="store_true", help="登录后读取课程分类和分页，生成配置候选")
    args = parser.parse_args()
    try:
        value = login(load_config(), on_authenticated=export_catalog if args.export_courses else None)
        save_cookie(value)
    except KeyboardInterrupt:
        print("已取消登录，未保存新 Cookie。")
        return 130
    except Exception as exc:
        print(f"登录或保存未完成（{type(exc).__name__}）。请检查浏览器及依赖；不输出凭据和异常详情。")
        return 1
    print('登录验证通过，已更新根目录 cookie.txt。使用该会话时请设置 cookie_source 为 file，再运行自检。未提交选课。')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
