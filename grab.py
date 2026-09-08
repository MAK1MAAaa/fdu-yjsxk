#!/usr/bin/env python3
"""兼容原有启动方式；实际实现位于 fdu_yjsxk 包。"""

from fdu_yjsxk.cli import entrypoint, main


if __name__ == "__main__":
    entrypoint()
