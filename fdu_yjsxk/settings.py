"""项目固定路径与配置加载、校验。"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

BASE_DIR = str(Path(__file__).resolve().parent.parent)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
COOKIE_PATH = os.path.join(BASE_DIR, "cookie.txt")
LOG_PATH = os.path.join(BASE_DIR, "grab.log")
DOMAIN = "yjsxk.fudan.edu.cn"


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        example = os.path.join(BASE_DIR, "config.example.json")
        hint = (
            f"找不到配置文件：{CONFIG_PATH}\n"
            f"请参考 {os.path.basename(example)} 创建你自己的配置：\n"
            f"  cp {os.path.basename(example)} config.json\n"
            f"然后填入你的课程代码（bjdm 需从选课系统抓取）。"
        )
        raise SystemExit(hint)
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict) -> None:
    for key, default in (
        ("request_interval", 0.8), ("round_interval", 0),
        ("homepage_refresh_secs", 1.0), ("cookie_refresh_secs", 240),
        ("poll_interval", 0.6), ("http_timeout", 12),
    ):
        value = float(cfg.get(key, default))
        minimum_inclusive = key in ("round_interval", "homepage_refresh_secs")
        if not math.isfinite(value) or value < 0 or (value == 0 and not minimum_inclusive):
            raise ValueError(f"{key} 必须是有限{'非负' if minimum_inclusive else '正'}数")
    for key, default in (("poll_max", 15), ("full_max_tries", 0)):
        value = cfg.get(key, default)
        if type(value) is not int or value < (1 if key == "poll_max" else 0):
            raise ValueError(f"{key} 必须是{'正' if key == 'poll_max' else '非负'}整数")
    if cfg.get("serial_mode", True) is not True:
        raise ValueError("当前版本仅支持串行选课，请设置 serial_mode: true")
    if cfg.get("cookie_source", "auto") not in ("auto", "browser", "file"):
        raise ValueError("cookie_source 仅支持 auto / browser / file")
    start = dt.datetime.strptime(cfg["start_time"], "%Y-%m-%d %H:%M:%S")
    end = dt.datetime.strptime(cfg["end_time"], "%Y-%m-%d %H:%M:%S")
    if end <= start:
        raise ValueError("end_time 必须晚于 start_time")
