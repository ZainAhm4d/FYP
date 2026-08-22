"""
In-process sliding-window rate limiter.

Suitable for the current single-worker deployment. If the app moves to
multiple Gunicorn workers or multiple hosts, replace the backing store with
Redis (each process would otherwise keep its own independent counters).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    """Track request timestamps per key; reject when the window is full."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_requests:
                retry_after = int(q[0] - cutoff) + 1
                return False, retry_after
            q.append(now)
            # Opportunistic cleanup so the dict doesn't grow unbounded
            if len(self._hits) > 10_000:
                stale = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
                for k in stale:
                    del self._hits[k]
            return True, 0


# Login: 10 attempts / 5 min per IP — slows credential stuffing without
# locking out a legitimate user who typos a few times.
login_limiter = SlidingWindowLimiter(max_requests=10, window_seconds=300)

# Registration: 5 accounts / hour per IP.
register_limiter = SlidingWindowLimiter(max_requests=5, window_seconds=3600)

# Upload: 20 uploads / 10 min per IP (parsing is CPU/memory heavy).
upload_limiter = SlidingWindowLimiter(max_requests=20, window_seconds=600)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce(limiter: SlidingWindowLimiter, request: Request, what: str) -> None:
    allowed, retry_after = limiter.check(_client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many {what} attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def limit_login(request: Request) -> None:
    _enforce(login_limiter, request, "login")


def limit_register(request: Request) -> None:
    _enforce(register_limiter, request, "registration")


def limit_upload(request: Request) -> None:
    _enforce(upload_limiter, request, "upload")
