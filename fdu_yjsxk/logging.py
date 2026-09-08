"""将运行信息同时输出到终端和项目根目录 grab.log。"""

from __future__ import annotations

import datetime as dt

from .settings import LOG_PATH


def log(msg: str = "") -> None:
    now = dt.datetime.now()
    millis = now.microsecond // 1000
    print(f"[{now:%H:%M:%S}.{millis:03d}] {msg}", flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{now:%Y-%m-%d %H:%M:%S}.{millis:03d}] {msg}\n")
    except OSError:
        pass
