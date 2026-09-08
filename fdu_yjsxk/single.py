"""非定时单课程捡漏：交互选择，只修改本次运行的配置副本。"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import time

from .logging import log
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


def build_single_config(cfg: dict, course: dict, minutes: int, now: dt.datetime) -> dict:
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"运行分钟数必须在 1 至 {MAX_MINUTES} 之间")
    result = deepcopy(cfg)
    result["courses"] = [deepcopy(course)]
    result["start_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
    result["end_time"] = (now + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    result["serial_mode"] = True
    result["full_max_tries"] = 0
    validate_config(result)
    return result


def run_single(cfg: dict) -> int:
    courses = available_courses(cfg)
    if not courses:
        print("config.json 中没有启用且未标记已选的课程，未发起任何选课请求。")
        return 0
    print("单课程捡漏：本次只尝试一门课，不修改 config.json。")
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
        f"运行分钟数（1—{MAX_MINUTES}，回车默认 {DEFAULT_MINUTES}，0 退出；确认后立即开始）：",
        MAX_MINUTES, DEFAULT_MINUTES,
    )
    if minutes == 0:
        print("已取消，未发起选课请求。")
        return 0
    session_cfg = build_single_config(cfg, course, minutes, dt.datetime.now())
    print(f"本次截止：{session_cfg['end_time']}；选上、已选或到时停止，Ctrl+C 可中止。")
    print("沿用请求间隔与 Cookie 设置；本次满额不限重试次数，服务器暂停要求仍有效。")
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
    log("请在选课系统的已选课程页核对最终状态。本汇总已写入 grab.log。")
    log("=" * 46)
    return code
