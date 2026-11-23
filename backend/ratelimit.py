"""NAT-friendly rate limiting for public endpoints.

At an event, hundreds of real people share one public IP (venue WiFi or a
carrier's NAT), so a strict per-IP limit would lock out the crowd.  Limits
are therefore layered:

* **per client** — a random, anonymous ``it_c`` cookie (strict);
* **per scope**  — e.g. per event or per tag (protects a target);
* **per IP**     — only a loose flood ceiling, keyed by the *hashed* IP.

Counters live in process memory: Render's free tier runs a single instance,
so this is exact there and costs zero database writes.  (Behind several
instances each one enforces its own share — documented in EVENT_MODE.md.)
"""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict, deque
from typing import Optional

from fastapi import Request, Response

from auth import hash_ip

CLIENT_COOKIE = "it_c"
MAX_KEYS = 50_000


class SlidingWindow:
    def __init__(self, max_keys: int = MAX_KEYS):
        self._hits: "OrderedDict[str, deque]" = OrderedDict()
        self.max_keys = max_keys

    def allow(self, key: str, limit: int, window: float, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        dq = self._hits.get(key)
        if dq is None:
            dq = deque()
            self._hits[key] = dq
            if len(self._hits) > self.max_keys:
                self._hits.popitem(last=False)
        else:
            self._hits.move_to_end(key)
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    def clear(self) -> None:
        self._hits.clear()


limiter = SlidingWindow()
_seen = SlidingWindow()  # short-lived de-dupe (e.g. scan counting)


def client_ip_hash(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "0.0.0.0")
    return hash_ip(ip)


def client_id(request: Request) -> Optional[str]:
    cid = request.cookies.get(CLIENT_COOKIE, "")
    return cid if 16 <= len(cid) <= 64 and cid.isalnum() else None


def ensure_client_cookie(request: Request, response: Response) -> str:
    cid = client_id(request)
    if cid:
        return cid
    cid = secrets.token_hex(16)
    response.set_cookie(
        CLIENT_COOKIE, cid, max_age=365 * 24 * 3600, httponly=True,
        secure=request.url.scheme == "https", samesite="lax", path="/",
    )
    return cid


def check(
    request: Request,
    action: str,
    *,
    per_client: tuple[int, float],
    per_ip: tuple[int, float],
    scope: Optional[str] = None,
    per_scope: Optional[tuple[int, float]] = None,
) -> bool:
    """True when the request is within every applicable limit."""
    ip_h = client_ip_hash(request)
    cid = client_id(request)
    # No cookie (blocked / first request) → identify by IP + user agent, which
    # still separates most phones behind the same NAT.
    who = cid or f"{ip_h}:{hash(request.headers.get('user-agent', ''))}"
    if not limiter.allow(f"{action}:c:{who}", *per_client):
        return False
    if scope and per_scope and not limiter.allow(f"{action}:s:{scope}", *per_scope):
        return False
    return limiter.allow(f"{action}:ip:{ip_h}", *per_ip)


def first_seen(key: str, window: float = 60.0) -> bool:
    """True the first time ``key`` is seen within ``window`` seconds."""
    return _seen.allow(key, 1, window)
