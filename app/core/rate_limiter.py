"""
Simple in-process sliding-window rate limiter, keyed by client IP.

Limitation (documented, not hidden): this is per-process/in-memory, so it
does not enforce a global limit across multiple running instances. In a
real multi-instance deployment this would be backed by Redis
(INCR + EXPIRE or a token-bucket Lua script) so all instances share state.
Kept in-memory here to keep the prototype dependency-free and runnable
with zero external infra.
"""
import time
import threading
from collections import defaultdict, deque
from app.core.config import settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_seconds:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True


rate_limiter = RateLimiter(settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS)
