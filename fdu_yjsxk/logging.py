"""将运行信息同时输出到终端和项目根目录 grab.log。"""

from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .settings import LOG_PATH

_write_file = ContextVar("write_log_file", default=True)


@contextmanager
def console_only() -> Iterator[None]:
    """仅在本上下文及其异步工作线程中关闭日志落盘。"""
    token = _write_file.set(False)
    try:
        yield
    finally:
        _write_file.reset(token)


def log(msg: str = "") -> None:
    now = dt.datetime.now()
    millis = now.microsecond // 1000
    print(f"[{now:%H:%M:%S}.{millis:03d}] {msg}", flush=True)
    if not _write_file.get():
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{now:%Y-%m-%d %H:%M:%S}.{millis:03d}] {msg}\n")
    except OSError:
        pass
