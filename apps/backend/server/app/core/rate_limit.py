from collections import OrderedDict, deque
from time import monotonic

from app.core.errors import BusinessError

_requests: OrderedDict[str, deque[float]] = OrderedDict()


def check_rate_limit(key: str, *, limit: int, window: int) -> None:
    """限制单进程内的密集请求，避免登录穷举和模型资源拥塞。"""
    now = monotonic()
    timestamps = _requests.setdefault(key, deque())
    _requests.move_to_end(key)
    while timestamps and timestamps[0] <= now - window:
        timestamps.popleft()
    if len(timestamps) >= limit:
        raise BusinessError(429, "请求过于频繁，请稍后重试")
    timestamps.append(now)
    while len(_requests) > 4096:
        _requests.popitem(last=False)
