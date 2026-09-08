"""命令行参数解析与统一退出码处理。"""

from __future__ import annotations

import argparse

from .diagnostics import dry_run, probe
from .errors import CookieError, DeadlineReached, TransientError
from .logging import log
from .runner import run
from .settings import load_config


def main() -> int:
    ap = argparse.ArgumentParser(description="复旦大学研究生选课脚本")
    ap.add_argument("--dry-run", action="store_true", help="只自检，不提交选课请求")
    ap.add_argument("--now", action="store_true", help="忽略 start_time，立即开始")
    ap.add_argument("--probe", action="store_true", help="链路演练：发 1 次真实请求看服务器回什么")
    ap.add_argument("--force", action="store_true", help="配合 --probe，开放后也允许演练")
    args = ap.parse_args()

    cfg = load_config()
    if args.dry_run:
        return dry_run(cfg)
    if args.probe:
        return probe(cfg, force=args.force)
    return run(cfg, start_now=args.now)


def entrypoint() -> None:
    try:
        code = main()
    except KeyboardInterrupt:
        log("\n已手动中止")
        code = 130
    except (CookieError, TransientError, DeadlineReached, ValueError) as exc:
        log(f"运行停止：{exc or '已到截止时间'}")
        code = 1
    raise SystemExit(code)
