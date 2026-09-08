"""区分登录失效、暂时网络故障、缓存维护和截止时间。"""

from __future__ import annotations




class CookieError(RuntimeError):
    """Cookie 无效 / 登录态失效等需要人工介入的错误。"""
    pass


class TransientError(RuntimeError):
    """网络或服务暂不可用；不据此判定 Cookie 失效。"""

    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


class CachePause(RuntimeError):
    """服务器正在进行每日数据缓存。"""


class DeadlineReached(RuntimeError):
    """已到截止时间，不再发送新请求。"""
