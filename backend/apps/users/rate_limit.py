"""Atomic rate limiting backed by Redis when configured, falling back to Django cache."""
from hashlib import sha256
import math
import time

from django.conf import settings
from django.core.cache import cache


_REDIS_INCR_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


def _redis_client():
    url = getattr(settings, "RATE_LIMIT_REDIS_URL", "")
    if not url:
        return None
    from redis import Redis
    return Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)


def _key_digest(raw):
    return sha256(str(raw).encode("utf-8")).hexdigest()


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return (request.META.get("REMOTE_ADDR") or "unknown").strip()


def check_and_increment(scope, identifier, *, limit, window_seconds):
    """Increment counter atomically; return (allowed: bool, retry_after_seconds: int)."""
    key = f"rl:{scope}:{_key_digest(identifier)}"
    client = _redis_client()
    if client is not None:
        count, ttl = client.eval(_REDIS_INCR_WINDOW_LUA, 1, key, int(window_seconds))
        retry_after = max(1, int(ttl if ttl and ttl > 0 else window_seconds))
        return int(count) <= int(limit), retry_after

    now = time.time()
    entry = cache.get(key)
    if not isinstance(entry, dict) or entry.get("expires_at", 0) <= now:
        entry = {"count": 0, "expires_at": now + window_seconds}
    entry["count"] += 1
    remaining = max(1, math.ceil(entry["expires_at"] - now))
    cache.set(key, entry, timeout=remaining)
    return entry["count"] <= int(limit), remaining


def check_counter(scope, identifier, *, limit, window_seconds):
    """Read-only check whether a rate-limit bucket is already exhausted."""
    key = f"rl:{scope}:{_key_digest(identifier)}"
    client = _redis_client()
    if client is not None:
        raw = client.get(key)
        count = int(raw) if raw is not None else 0
        if count < int(limit):
            return True, 0
        ttl = client.ttl(key)
        return False, max(1, int(ttl if ttl and ttl > 0 else window_seconds))

    now = time.time()
    entry = cache.get(key)
    if not isinstance(entry, dict) or entry.get("expires_at", 0) <= now:
        return True, 0
    if entry.get("count", 0) < int(limit):
        return True, 0
    return False, max(1, math.ceil(entry["expires_at"] - now))


def clear_counter(scope, identifier):
    key = f"rl:{scope}:{_key_digest(identifier)}"
    client = _redis_client()
    if client is not None:
        client.delete(key)
        return
    cache.delete(key)


def check_and_set_cooldown(scope, identifier, *, cooldown_seconds):
    """Enforce minimum spacing between actions; return (allowed: bool, retry_after_seconds: int)."""
    key = f"cd:{scope}:{_key_digest(identifier)}"
    client = _redis_client()
    if client is not None:
        acquired = client.set(key, "1", ex=int(cooldown_seconds), nx=True)
        if acquired:
            return True, 0
        ttl = client.ttl(key)
        return False, max(1, int(ttl if ttl and ttl > 0 else cooldown_seconds))

    now = time.time()
    expires_at = cache.get(key)
    if expires_at is not None and expires_at > now:
        return False, max(1, math.ceil(expires_at - now))
    cache.set(key, now + cooldown_seconds, timeout=int(cooldown_seconds))
    return True, 0
