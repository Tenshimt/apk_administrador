"""In-memory rate limiter (Redis optional future upgrade)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from config import get_settings

settings = get_settings()

_buckets: dict[str, deque] = defaultdict(deque)


def _check_rate(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket = _buckets[key]
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    bucket.append(now)


def auth_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"auth:{ip}"
    _check_rate(key, settings.auth_rate_limit_requests, settings.auth_rate_limit_window_seconds)
