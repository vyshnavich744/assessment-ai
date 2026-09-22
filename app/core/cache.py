"""
Small TTL + LRU-ish cache in front of the DB for the hot redirect path
(GET /{code}). Redirects are read-heavy and latency-sensitive, so caching
the code -> long_url mapping avoids a DB hit on every click.

Limitation: process-local cache, not shared across instances, and not
invalidated instantly if a URL is deleted from another instance -- entries
expire within CACHE_TTL_SECONDS at worst. In production this would be
Redis/Memcached shared across instances with explicit invalidation on
delete. Documented trade-off, acceptable for a prototype.
"""
import time
import threading
from collections import OrderedDict
from app.core.config import settings


class TTLCache:
    def __init__(self, max_entries: int, ttl_seconds: int):
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._store: "OrderedDict[str, tuple[float, object]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            ts, value = item
            if time.time() - ts > self.ttl_seconds:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value):
        with self._lock:
            self._store[key] = (time.time(), value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def invalidate(self, key: str):
        with self._lock:
            self._store.pop(key, None)


redirect_cache = TTLCache(settings.CACHE_MAX_ENTRIES, settings.CACHE_TTL_SECONDS)
