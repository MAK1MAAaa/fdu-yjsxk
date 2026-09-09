"""非定时单课程捡漏：交互选择，只修改本次运行的配置副本。"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import math
import time

from .logging import console_only, log
from .runner import run
from .settings import validate_config


DEFAULT_MINUTES = 120
MAX_MINUTES = 1440


def available_courses(cfg: dict) -> list[dict]:
    return [
        course for course in cfg["courses"]
        if course.get("enabled", True) and not course.get("selected", False)
    ]


def read_number(prompt: str, maximum: int, default: int | None = None) -> int:
    """读取单个整数，0 或输入流关闭表示取消，不接受多个编号。"""
    while True:
        try:
            raw = input(prompt).strip()
        except EOFError:
            return 0
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            value = -1
        if 0 <= value <= maximum:
            return value
        print(f"请输入 1 至 {maximum} 的单个整数，或输入 0 退出。")


def validate_request_interval(value: float) -> float:
    if not math.isfinite(value) or not 0.1 <= value <= 60:
        raise ValueError("请求间隔必须是 0.1—60 秒之间的有限数字")
    return value


def read_request_interval(default: float) -> float | None:
    while True:
        try:
            raw = input(
                f"请求间隔秒数（0.1—60，回车默认 {default:g}，0 退出；确认后立即开始）："
            ).strip()
        except EOFError:
            return None
        try:
            value = float(raw) if raw else default
            if value == 0:
                return None
            return validate_request_interval(value)
        except ValueError as exc:
            print(f"输入无效：{exc}")


def build_single_config(
    cfg: dict, course: dict, minutes: int, now: dt.datetime,
    request_interval: float | None = None,
) -> dict:
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"运行分钟数必须在 1 至 {MAX_MINUTES} 之间")
    result = deepcopy(cfg)
    result["courses"] = [deepcopy(course)]
    result["start_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
    result["end_time"] = (now + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    result["serial_mode"] = True
    result["full_max_tries"] = 0
    if request_interval is not None:
        result["request_interval"] = validate_request_interval(request_interval)
    validate_config(result)
    return result


@console_only()
def run_single(cfg: dict) -> int:
    courses = available_courses(cfg)
    if not courses:
        print("config.json 中没有启用且未标记已选的课程，未发起任何选课请求。")
        return 0
    print("单课程捡漏：直接串行提交一门课，不先查余量，不修改 config.json，不保存日志文件。")
    print("请勿同时运行其他抢课脚本；列表来自本地配置，不是实时已选课程查询。")
    for index, course in enumerate(courses, 1):
        print(f"  {index}. {course['name']}（{course['bjdm']}）")
    choice = read_number("请选择一个课程编号（0 退出）：", len(courses))
    if choice == 0:
        print("已取消，未发起选课请求。")
        return 0
    course = courses[choice - 1]
    print(f"本次目标：{course['name']}（{course['bjdm']}）")
    minutes = read_number(
        f"运行分钟数（1—{MAX_MINUTES}，回车默认 {DEFAULT_MINUTES}，0 退出）：",
        MAX_MINUTES, DEFAULT_MINUTES,
    )
    if minutes == 0:
        print("已取消，未发起选课请求。")
        return 0
    interval = read_request_interval(float(cfg.get("request_interval", 0.8)))
    if interval is None:
        print("已取消，未发起选课请求。")
        return 0
    session_cfg = build_single_config(cfg, course, minutes, dt.datetime.now(), interval)
    print(f"本次截止：{session_cfg['end_time']}；选上、已选或到时停止，Ctrl+C 可中止。")
    print(f"本次请求间隔 {interval:g} 秒；这是结果返回后的等待，不是固定每秒请求数。")
    print("沿用主页刷新、Cookie 与轮询设置；满额持续重试，服务器暂停和退避要求仍有效。")
    started = time.monotonic()
    code = run(session_cfg, start_now=True)
    elapsed = time.monotonic() - started
    log("=" * 46)
    log("单课程捡漏成果汇总（选课进程已停止）")
    log(f"目标课程：{course['name']}（{course['bjdm']}）")
    log(f"结束时间：{dt.datetime.now():%Y-%m-%d %H:%M:%S}；本次耗时：{elapsed:.1f} 秒")
    if code == 0:
        log("结果：目标已选上或系统已提示已选，具体以本次上方返回信息为准。")
        log("已自动停止，不会继续重试，也不会转抢其他课程。")
    else:
        log("结果：未选上、尚未确认或运行失败，不计为成功；请查看上方原因。")
    log("请在选课系统的已选课程页核对最终状态。本汇总仅显示在终端，不写日志文件。")
    log("=" * 46)
    return code
