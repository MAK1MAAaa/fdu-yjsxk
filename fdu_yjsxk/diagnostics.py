"""登录态只读自检与单次真实选课链路演练。"""

from __future__ import annotations

import datetime as dt

from .client import Grabber
from .cookies import obtain_cookie
from .errors import CookieError, TransientError
from .logging import log
from .settings import DOMAIN


def dry_run(cfg: dict) -> int:
    log("=== 自检模式（不会提交任何选课请求）===")
    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    log(f"目标站点：http://{cfg.get('target', DOMAIN)}")
    log(f"开抢时间：{cfg.get('start_time')}   结束：{cfg.get('end_time')}")
    log(f"启用课程：{len(pending)} / {len(cfg['courses'])} 门")
    for c in pending:
        log(f"  · {c['name']:<20} {c['bjdm']}  lx={c['lx']} bqmc={c['bqmc']}")
    for c in cfg["courses"]:
        if not c.get("enabled", True):
            status = "已选，已停用" if c.get("selected", False) else "已停用"
            log(f"  · {c['name']:<20} （{status}）")

    log("")
    log("正在获取 Cookie ...")
    try:
        cookie = obtain_cookie(cfg)
    except CookieError as exc:
        log(f"✗ 取 Cookie 失败：{exc}")
        return 1
    names = [seg.strip().split("=")[0] for seg in cookie.split(";") if "=" in seg]
    log(f"✓ 取到 Cookie，共 {len(names)} 个字段：{', '.join(names)}")

    must = {"JSESSIONID", "_WEU"}
    missing = must - set(names)
    if missing:
        log(f"✗ 缺少关键字段：{', '.join(missing)} —— 请先在浏览器登录选课系统")
        return 1

    gr = Grabber(cfg, cookie)
    try:
        token = gr.refresh_token()
    except (CookieError, TransientError) as exc:
        log(f"✗ {exc}")
        return 1
    log("✓ Cookie 有效，已取得 CSRF Token")

    log("")
    log("=== 自检通过 ===")
    log("可以开抢了：双击「一键抢课.command」，或运行 uv run --locked python grab.py")
    return 0


def probe(cfg: dict, force: bool) -> int:
    """链路演练：对第一门启用的课程发 1 次真实选课请求，打印服务器原话。"""
    log("=== 链路演练（只发 1 次请求，不重试、不循环）===")
    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    if not pending:
        log("没有启用任何课程，退出")
        return 1

    start_time = dt.datetime.strptime(cfg["start_time"], "%Y-%m-%d %H:%M:%S")
    opened = dt.datetime.now() >= start_time
    if opened and not force:
        log(f"已过开抢时间（{start_time}），演练会真的提交一次选课请求。")
        log("确认要继续，请在命令末尾加 --force")
        return 1
    if opened:
        log("注意：选课已开放，本次演练等同于真的抢这门课。")

    c = pending[0]
    log(f"演练课程：{c['name']}（{c['bjdm']}）")

    try:
        cookie = obtain_cookie(cfg)
    except CookieError as exc:
        log(f"✗ 取 Cookie 失败：{exc}")
        return 1
    gr = Grabber(cfg, cookie)
    try:
        gr.refresh_token()
    except (CookieError, TransientError) as exc:
        log(f"✗ {exc}")
        return 1
    log("✓ Cookie 有效，已取得 CSRF Token")

    log("发送选课请求 ...")
    body = gr.probe_once(c)
    code = body.get("code")
    log(f"服务器返回：HTTP {body.get('http')}  code={code}")
    log(f"服务器原话：{body.get('msg') or '(无 msg 字段)'}")

    if code == 0:
        log("")
        log("=== 演练结论 ===")
        log("服务器拒绝了该请求（code=0），但这恰恰证明链路是通的：")
        log("  · Cookie 与 csrfToken 被接受（否则会跳登录页，根本取不到 token）")
        log("  · bjdm / lx / bqmc 被正确解析（否则会报参数错误）")
        log("  唯一的阻碍就是上面那句原话。条件满足后即可正常选课。")
        return 0

    if code is None:
        log("")
        log("=== 演练结论 ===")
        log("响应不是预期格式，多半是 Cookie 失效或接口有变，请勿直接开抢。")
        return 1

    log("服务器已受理，轮询最终结果 ...")
    rcode, rmsg = gr.poll_result(body.get("msg") or "")
    log(f"最终结果：code={rcode}  msg={rmsg or '(空)'}")
    if rcode == 1:
        log("★ 真的选上了！请到「已选课程」页确认。")
    else:
        log("未选上，原因见上。")
    return 0
