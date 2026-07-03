"""Public-URL resolution for QR codes, sticker PDFs and share links.

The QR must contain an ABSOLUTE https URL or phone cameras show dead text
instead of opening the finder page.  Deployments that set SITE_URL win;
otherwise we derive the origin from the incoming request (honouring the
reverse-proxy forwarding headers nginx / PaaS load balancers send).
"""
from __future__ import annotations

import os

from fastapi import Request


def resolve_site_url(request: Request | None = None) -> str:
    """Best absolute origin for public links, without a trailing slash."""
    env = os.environ.get("SITE_URL", "").strip().rstrip("/")
    if env:
        return env
    if request is None:
        return ""
    proto = request.headers.get("x-forwarded-proto", "") or request.url.scheme or "https"
    host = (
        request.headers.get("x-forwarded-host", "")
        or request.headers.get("host", "")
        or request.url.netloc
    )
    # Multiple proxies may append comma-separated values — take the first.
    proto = proto.split(",")[0].strip()
    host = host.split(",")[0].strip()
    if not host:
        return ""
    return f"{proto}://{host}"


def site_domain(request: Request | None = None) -> str:
    """Bare domain for printing on stickers (e.g. 'info-tag.in')."""
    url = resolve_site_url(request)
    return url.split("://", 1)[-1] if url else "info-tag.in"
