"""命令行参数解析与统一退出码处理。"""

from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import nullcontext
import sys

from .diagnostics import dry_run, probe
from .errors import CookieError, DeadlineReached, TransientError
from .logging import console_only, log
from .runner import run
from .settings import load_config
from .single import read_request_interval, run_single


def main() -> int:
    ap = argparse.ArgumentParser(description="复旦大学研究生选课脚本")
    ap.add_argument("--dry-run", action="store_true", help="只自检，不提交选课请求")
    ap.add_argument("--now", action="store_true", help="忽略 start_time，立即开始")
    ap.add_argument("--probe", action="store_true", help="链路演练：发 1 次真实请求看服务器回什么")
    ap.add_argument("--force", action="store_true", help="配合 --probe，开放后也允许演练")
    ap.add_argument("--single", action="store_true", help="数字选择一门课，设置时长与请求间隔后捡漏")
    ap.add_argument("--ask-interval", action="store_true", help="交互设置本次请求间隔，保留配置起止时间")
    args = ap.parse_args()
    if args.ask_interval and (args.single or args.dry_run or args.probe or args.force):
        ap.error("--ask-interval 不与 --single/--dry-run/--probe/--force 同用")
    if args.single and (args.dry_run or args.now or args.probe or args.force):
        ap.error("--single 请单独使用，不能与 --dry-run/--now/--probe/--force 同用")

    cfg = load_config()
    if args.single:
        return run_single(cfg)
    if args.dry_run:
        return dry_run(cfg)
    if args.probe:
        return probe(cfg, force=args.force)
    if args.ask_interval:
        interval = read_request_interval(float(cfg.get("request_interval", 0.8)))
        if interval is None:
            print("已取消，未启动选课。")
            return 0
        cfg = deepcopy(cfg)
        cfg["request_interval"] = interval
        print(f"本次请求间隔 {interval:g} 秒；只对本次生效，不修改 config.json。")
        print(f"配置开始：{cfg['start_time']}；截止：{cfg['end_time']}；课程顺位保持不变。")
    return run(cfg, start_now=args.now)


def entrypoint() -> None:
    with console_only() if "--single" in sys.argv[1:] else nullcontext():
        try:
            code = main()
        except KeyboardInterrupt:
            log("\n已手动中止")
            code = 130
        except (CookieError, TransientError, DeadlineReached, ValueError) as exc:
            log(f"运行停止：{exc or '已到截止时间'}")
            code = 1
    raise SystemExit(code)
