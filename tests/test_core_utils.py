import time
from app.core.rate_limiter import RateLimiter
from app.core.cache import TTLCache
from app.core.shortcode import generate_code


def test_rate_limiter_allows_up_to_limit_then_blocks():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    assert rl.allow("client-a") is True
    assert rl.allow("client-a") is True
    assert rl.allow("client-a") is True
    assert rl.allow("client-a") is False  # 4th request in window is blocked


def test_rate_limiter_is_per_key():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    assert rl.allow("client-a") is True
    assert rl.allow("client-b") is True  # different key, independent budget


def test_rate_limiter_window_expiry():
    rl = RateLimiter(max_requests=1, window_seconds=0.05)
    assert rl.allow("client-a") is True
    assert rl.allow("client-a") is False
    time.sleep(0.06)
    assert rl.allow("client-a") is True


def test_ttl_cache_set_get_and_expiry():
    cache = TTLCache(max_entries=10, ttl_seconds=0.05)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    time.sleep(0.06)
    assert cache.get("k1") is None


def test_ttl_cache_eviction_at_capacity():
    cache = TTLCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # should evict "a" (least recently used)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_generate_code_length_and_alphabet():
    code = generate_code(7)
    assert len(code) == 7
    assert code.isalnum()
