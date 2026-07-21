"""Public site endpoints — visit counting, live stats, and feedback.

Privacy notes
-------------
* Visits are counted with a salted SHA-256 hash of the visitor IP, deduped
  per calendar day — no raw IPs, no cookies, no fingerprinting.
* Feedback is honeypot-protected and rate-limited per hashed IP per day.
* Only feedback explicitly approved by the admin (``is_public=True``) is
  ever returned by the public testimonial endpoint.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from auth import hash_ip
from db import get_db
from models import FeedbackCreatePayload

router = APIRouter(prefix="/api/public", tags=["public"])

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(text: str, limit: int = 1000) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()[:limit]


def _client_ip(request: Request) -> str:
    """Prefer the left-most X-Forwarded-For entry (matches scan tracking)."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


# ---------------------------------------------------------------------------
# Visit counting (unique-ish per hashed-IP per day; zero PII)
# ---------------------------------------------------------------------------
@router.post("/visit")
async def record_visit(request: Request) -> dict:
    db = get_db()
    ip_h = hash_ip(_client_ip(request))
    day = datetime.now(timezone.utc).date().isoformat()
    try:
        # Unique index on (ip_hash, day) makes this idempotent per visitor/day.
        await db.visits.update_one(
            {"ip_hash": ip_h, "day": day},
            {
                "$setOnInsert": {
                    "id": f"visit_{uuid.uuid4().hex[:12]}",
                    "ip_hash": ip_h,
                    "day": day,
                    "first_seen_at": datetime.now(timezone.utc).isoformat(),
                    "user_agent": request.headers.get("user-agent", "")[:200],
                },
                "$inc": {"hits": 1},
            },
            upsert=True,
        )
    except Exception:  # noqa: BLE001 — visit counting must never break the app
        pass
    return {"ok": True}


# ---------------------------------------------------------------------------
# Public site settings — which landing sections the admin has switched on
# ---------------------------------------------------------------------------
@router.get("/site-settings")
async def public_site_settings() -> dict:
    from routes.admin_routes import get_site_settings

    try:
        return await get_site_settings(get_db())
    except Exception:  # noqa: BLE001 — the landing page must render regardless
        return {"landing_sections": {}}


# ---------------------------------------------------------------------------
# Public live stats for the landing page ("social proof" counters)
# ---------------------------------------------------------------------------
@router.get("/stats")
async def public_stats() -> dict:
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    visitors_total = await db.visits.count_documents({})
    visitors_today = await db.visits.count_documents({"day": today})
    scans_total = await db.scans.count_documents({})
    found_reports = await db.messages.count_documents({"action_type": "found"})
    items_recovered = await db.tags.count_documents({"status": "found"})
    tags_active = await db.tags.count_documents({"status": {"$ne": "found"}})
    return {
        "visitors_total": visitors_total,
        "visitors_today": visitors_today,
        "scans_total": scans_total,
        "found_reports": found_reports,
        "items_recovered": items_recovered,
        "tags_active": tags_active,
    }


# ---------------------------------------------------------------------------
# Feedback / comments
# ---------------------------------------------------------------------------
@router.post("/feedback")
async def submit_feedback(payload: FeedbackCreatePayload, request: Request) -> dict:
    if payload.bot_check:
        return {"ok": True, "id": "blocked"}  # silently drop bots

    body = _sanitize(payload.message, 1000)
    if not body:
        raise HTTPException(status_code=400, detail="Feedback message is required")

    db = get_db()
    ip_h = hash_ip(_client_ip(request))
    today = datetime.now(timezone.utc).date().isoformat()

    # Rate limit: max 3 feedback entries per hashed IP per day.
    sent_today = await db.feedback.count_documents(
        {"ip_hash": ip_h, "created_at": {"$gte": today}}
    )
    if sent_today >= 3:
        raise HTTPException(status_code=429, detail="Feedback limit reached for today. Thank you!")

    doc = {
        "id": f"fb_{uuid.uuid4().hex[:12]}",
        "name": _sanitize(payload.name, 120),
        "email": _sanitize(payload.email, 160),
        "message": body,
        "rating": max(1, min(5, int(payload.rating or 5))),
        "is_public": False,  # admin must approve before it shows publicly
        "ip_hash": ip_h,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.feedback.insert_one(doc)
    return {"ok": True, "id": doc["id"]}


@router.get("/feedback")
async def public_feedback() -> list[dict]:
    """Only admin-approved feedback, newest first, capped at 12."""
    db = get_db()
    docs = (
        await db.feedback.find(
            {"is_public": True},
            {"_id": 0, "ip_hash": 0, "email": 0},  # never expose email/IP hash
        )
        .sort("created_at", -1)
        .to_list(12)
    )
    return docs
