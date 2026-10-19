"""Rate limiter: counts only failed attempts. Keys: email + store_slug + IP."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from config import get_settings

settings = get_settings()

_failures: dict[str, deque] = defaultdict(deque)


def _get_ip(request: Request) -> str:
    if settings.trusted_proxy:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune(key: str) -> None:
    bucket = _failures[key]
    cutoff = time.monotonic() - settings.auth_rate_limit_window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def check_rate_limit(key: str) -> None:
    _prune(key)
    if len(_failures[key]) >= settings.auth_rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
        )


def record_failure(key: str) -> None:
    _failures[key].append(time.monotonic())


def reset_key(key: str) -> None:
    _failures.pop(key, None)


def login_rate_key(request: Request, email: str, store_slug: str) -> str:
    ip = _get_ip(request)
    return f"login:{email}:{store_slug}:{ip}"


def register_rate_key(request: Request) -> str:
    ip = _get_ip(request)
    return f"register:{ip}"


# Legacy alias used by conftest reset fixture
_buckets = _failures


def auth_rate_limit(request: Request) -> None:
    """Kept for any remaining direct Depends() usage."""
    ip = _get_ip(request)
    key = f"auth:{ip}"
    check_rate_limit(key)
    record_failure(key)
