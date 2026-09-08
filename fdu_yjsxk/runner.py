"""串行选课流程、定时等待、结果处理和异常恢复。"""

from __future__ import annotations

import datetime as dt
import time

from .client import Grabber
from .cookies import obtain_cookie
from .errors import CachePause, CookieError, DeadlineReached, TransientError
from .logging import log
from .settings import validate_config


def cache_resume_at(now: dt.datetime, interval: float) -> dt.datetime:
    release = now.replace(hour=13, minute=0, second=0, microsecond=0)
    if now < release:
        return release
    return now + dt.timedelta(seconds=max(interval, 0.8))


def already_have(msg: str) -> bool:
    """结果里出现这些话，说明这门课其实已经在已选列表里了，不必再重试。"""
    if not msg:
        return False
    failure_hints = ("已选满", "已选人数", "人数已满", "容量已满", "名额已满")
    if any(hint in msg for hint in failure_hints):
        return False
    selected_hints = (
        "已经选择过",
        "已经选过",
        "已选择该课程",
        "已选过该课程",
        "重复选课",
        "重复选择",
        "不可重复",
        "不能重复",
    )
    return any(hint in msg for hint in selected_hints)


def handle_result(
    course: dict, code, msg: str, done: list, pending: list, gr: Grabber
) -> None:
    """处理一门课的选课结果：成了就从待抢列表里去掉。"""
    name, bjdm = course["name"], course["bjdm"]
    if "数据缓存中" in msg and "13:00:00" in msg:
        raise CachePause(msg)
    if code == 1:
        log(f"  ★ 选上 {name}（{bjdm}）")
        done.append(name)
        pending.remove(course)
        return
    if already_have(msg or ""):
        log(f"  ✓ {name} 已在已选列表中（{msg}），跳过")
        done.append(name)
        pending.remove(course)
        return
    if "#6qz9u" in msg or any(
        hint in msg for hint in ("容量已满", "名额已满", "人数已满", "教学班已满")
    ):
        gr.full_tries[bjdm] += 1
        limit = int(gr.cfg.get("full_max_tries", 0))
        if limit > 0 and gr.full_tries[bjdm] >= limit:
            gr.exhausted.append(course)
            pending.remove(course)
            log(f"  {name}：满额累计 {limit} 次，本次停止尝试，仍未选上")
            return
    log(f"  × {name} 未成功：{msg or '未知原因'}")


def run_serial(gr: Grabber, pending: list, done: list, interval: float) -> None:
    """按顺位逐门提交，确认当前受理号的结果后再处理下一门。"""
    courses = (
        [c for c in pending if c["bjdm"] in gr.inflight]
        if gr.inflight else list(pending)
    )
    for c in courses:
        gr.check_deadline()
        xid = gr.inflight.get(c["bjdm"])
        if xid is None:
            ok, info = gr.submit(c)
            if not ok:
                handle_result(c, None, info, done, pending, gr)
                gr.pause(interval)
                continue
            xid = info
            gr.inflight[c["bjdm"]] = xid
            log(f"  已提交 {c['name']}（{c['bjdm']}），等待结果 ...")
        code, msg = gr.poll_result(xid)
        if code is None and not already_have(msg):
            log(f"  {c['name']}：{msg}；保留受理号，继续查询，暂不提交其他课程")
            gr.pause(interval)
            return
        del gr.inflight[c["bjdm"]]
        handle_result(c, code, msg, done, pending, gr)
        gr.pause(interval)


def wait_until(target: dt.datetime, label: str) -> None:
    """等到 target；超时不自动 +1 天（原脚本会静默等到明天）。"""
    while True:
        remain = (target - dt.datetime.now()).total_seconds()
        if remain <= 0:
            return
        if remain > 600:
            step = 60
        elif remain > 60:
            step = 30
        elif remain > 10:
            step = 5
        else:
            step = 1
        h, rem = divmod(int(remain), 3600)
        m, s = divmod(rem, 60)
        log(f"{label}：还有 {h}小时{m}分{s}秒")
        time.sleep(min(step, remain))


def wait_until_with_keepalive(
    target: dt.datetime,
    label: str,
    gr: "Grabber",
    cfg: dict,
    refresh_secs: float,
) -> None:
    """等待期间定期访问选课页，防止浏览器登录态因长时间空闲而过期。"""
    last_refresh_ts = time.monotonic()
    while True:
        gr.check_deadline()
        remain = (target - dt.datetime.now()).total_seconds()
        if remain <= 0:
            return

        if time.monotonic() - last_refresh_ts >= refresh_secs:
            try:
                changed = gr.set_cookie(obtain_cookie(cfg))
                gr.refresh_token()
                suffix = "（Cookie 已更新）" if changed else ""
                log(f"{label}：登录态已续期{suffix}")
            except (CookieError, TransientError) as exc:
                log(f"{label}：登录态续期失败，将继续重试：{exc}")
            finally:
                last_refresh_ts = time.monotonic()

        remain = (target - dt.datetime.now()).total_seconds()
        if remain <= 0:
            return

        if remain > 600:
            step = 60
        elif remain > 60:
            step = 30
        elif remain > 10:
            step = 5
        else:
            step = 1
        h, rem = divmod(int(remain), 3600)
        m, s = divmod(rem, 60)
        log(f"{label}：还有 {h}小时{m}分{s}秒")
        gr.pause(min(step, remain))


def countdown_banner(deadline: dt.datetime, n_courses: int) -> None:
    log("=" * 46)
    log("  复旦研究生选课 · 已就绪")
    log(f"  目标时间 {deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  待抢课程 {n_courses} 门")
    log("=" * 46)


def run(cfg: dict, start_now: bool) -> int:
    validate_config(cfg)
    interval = float(cfg.get("request_interval", 0.8))
    round_interval = float(cfg.get("round_interval", 0))
    refresh_secs = float(cfg.get("cookie_refresh_secs", 240))
    end_time = dt.datetime.strptime(cfg["end_time"], "%Y-%m-%d %H:%M:%S")
    start_time = dt.datetime.strptime(cfg["start_time"], "%Y-%m-%d %H:%M:%S")
    if dt.datetime.now() >= end_time:
        log(f"配置截止时间 {end_time} 已过，请修改 start_time / end_time 后再运行")
        return 1

    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    if not pending:
        log("没有启用任何课程，退出")
        return 0

    # ---- 取 Cookie 并自检 ----
    log("正在获取 Cookie ...")
    try:
        cookie = obtain_cookie(cfg)
        gr = Grabber(cfg, cookie)
        gr.deadline = end_time
        gr.refresh_token()
    except (CookieError, TransientError, DeadlineReached) as exc:
        log(f"初始化未完成：{exc or '已到截止时间'}")
        return 1
    log("Cookie 有效，已取得 CSRF Token")
    log(
        f"请求间隔 {interval}s；轮次间隔 {round_interval}s；"
        f"主页刷新最短间隔 {cfg.get('homepage_refresh_secs', 1.0)}s；"
        f"满额上限 {cfg.get('full_max_tries', 0)}（0=不限）；截止 {end_time}"
    )

    if start_now:
        log("（--now：跳过等待，立即开始）")
    else:
        if start_time < dt.datetime.now():
            log("=" * 46)
            log(f"  注意：start_time（{start_time}）已经过去了")
            log("  脚本不会自动改到明天，现在直接开始。")
            log("=" * 46)
        else:
            countdown_banner(start_time, len(pending))
            # 临近开抢前 3 分钟换一次新 Cookie，避免等待期间过期
            prewarm = start_time - dt.timedelta(seconds=180)
            if prewarm > dt.datetime.now():
                wait_until_with_keepalive(
                    prewarm,
                    "等待换票点",
                    gr,
                    cfg,
                    refresh_secs,
                )
                log("临近开抢，重新获取一次最新 Cookie ...")
                try:
                    gr.set_cookie(obtain_cookie(cfg))
                    gr.refresh_token()
                    log("已读取最新 Cookie 并刷新 CSRF Token")
                except (CookieError, TransientError) as exc:
                    log(f"换新票失败（继续用旧票）：{exc}")
            wait_until(start_time, "等待开抢")

    # ---- 正式抢课 ----
    log("开始抢课！（串行模式：一门结果出来再选下一门）")
    last_cookie_ts = time.monotonic()
    done: list = []
    round_no = 0
    failures = 0

    while pending and dt.datetime.now() < end_time:
        round_no += 1
        try:
            if not gr.inflight:
                if time.monotonic() - last_cookie_ts >= refresh_secs:
                    try:
                        changed = gr.set_cookie(obtain_cookie(cfg))
                        if changed:
                            log("检测到浏览器 Cookie 更新，已切换到新会话")
                    except CookieError as exc:
                        log(f"读取新 Cookie 失败，继续当前会话：{exc}")
                    finally:
                        last_cookie_ts = time.monotonic()
                gr.ensure_token()
            run_serial(gr, pending, done, interval)
        except DeadlineReached:
            break
        except CachePause:
            resume = min(cache_resume_at(dt.datetime.now(), interval), end_time)
            log(f"服务器数据缓存中，等待至 {resume:%H:%M:%S} 后从第一顺位重试")
            gr.token = None
            if resume < end_time:
                wait_until_with_keepalive(resume, "等待缓存结束", gr, cfg, refresh_secs)
            else:
                gr.pause((resume - dt.datetime.now()).total_seconds())
            continue
        except CookieError as exc:
            gr.token = None
            log(f"回合 {round_no}：{exc}；重新读取 Cookie")
            try:
                gr.set_cookie(obtain_cookie(cfg))
                gr.refresh_token()
                last_cookie_ts = time.monotonic()
                failures = 0
                log("已恢复")
            except DeadlineReached:
                break
            except (CookieError, TransientError) as exc2:
                failures += 1
                delay = min(12, 2 ** min(failures - 1, 4))
                log(f"恢复失败：{exc2}；{delay}s 后重试")
                gr.pause(delay)
            continue
        except TransientError as exc:
            failures += 1
            delay = max(exc.retry_after, min(12, 2 ** min(failures - 1, 4)))
            log(f"网络/服务暂不可用：{exc}；{delay}s 后重试")
            gr.pause(delay)
            continue
        failures = 0
        if pending:
            gr.pause(round_interval)

    log("-" * 46)
    if done:
        log(f"成功 {len(done)} 门：")
        for name in done:
            log(f"  · {name}")
    unfinished = pending + gr.exhausted
    if unfinished:
        log(f"未拿下或尚未确认 {len(unfinished)} 门：")
        for c in unfinished:
            log(f"  · {c['name']}（{c['bjdm']}）")
    if gr.inflight:
        log("仍有受理号未确认最终结果，请在「已选课程」页核对，勿视为确定失败")
    gr.session.close()
    log("结束。请到「已选课程」页核对。")
    return 0 if not unfinished else 1
