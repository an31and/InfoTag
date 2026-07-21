"""Admin-only endpoints — dashboard stats, feedback moderation, sponsor intents.

Access model
------------
Single-owner admin portal. A user document with ``role == "admin"`` (seeded
from ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` at boot) is required for every
endpoint here. Authorization is enforced **server-side** via the
``_require_admin`` dependency — hiding the UI is not the security boundary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_current_user
from db import get_db
from notifications import whatsapp_config_status, whatsapp_probe, whatsapp_send_debug

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(request: Request) -> dict:
    user = await get_current_user(request, get_db())
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------
@router.get("/stats")
async def admin_stats(admin: dict = Depends(_require_admin)) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    visitors_total = await db.visits.count_documents({})
    visitors_today = await db.visits.count_documents({"day": today})
    visitors_7d = await db.visits.count_documents({"day": {"$gte": (now - timedelta(days=7)).date().isoformat()}})

    scans_total = await db.scans.count_documents({})
    scans_today = await db.scans.count_documents({"scanned_at": {"$gte": today}})
    scans_7d = await db.scans.count_documents({"scanned_at": {"$gte": week_ago}})

    found_reports = await db.messages.count_documents({"action_type": "found"})
    items_recovered = await db.tags.count_documents({"status": "found"})
    tags_lost = await db.tags.count_documents({"status": "lost"})

    users_total = await db.users.count_documents({})
    tags_total = await db.tags.count_documents({})
    messages_total = await db.messages.count_documents({})
    feedback_total = await db.feedback.count_documents({})
    feedback_pending = await db.feedback.count_documents({"is_public": False})
    sponsors_total = await db.sponsors.count_documents({})

    return {
        "visitors": {"total": visitors_total, "today": visitors_today, "last_7d": visitors_7d},
        "scans": {"total": scans_total, "today": scans_today, "last_7d": scans_7d},
        "found": {"reports": found_reports, "items_recovered": items_recovered, "currently_lost": tags_lost},
        "users_total": users_total,
        "tags_total": tags_total,
        "messages_total": messages_total,
        "feedback": {"total": feedback_total, "pending_review": feedback_pending},
        "sponsors_total": sponsors_total,
        "generated_at": now.isoformat(),
    }


@router.get("/scans/daily")
async def scans_daily(days: int = 14, admin: dict = Depends(_require_admin)) -> list[dict]:
    """Scans-per-day for the last N days (for a small trend chart)."""
    db = get_db()
    days = max(1, min(days, 90))
    start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = db.scans.aggregate(
        [
            {"$match": {"scanned_at": {"$gte": start}}},
            {"$group": {"_id": {"$substr": ["$scanned_at", 0, 10]}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    )
    rows = await cursor.to_list(days + 1)
    return [{"day": r["_id"], "count": r["count"]} for r in rows]


# ---------------------------------------------------------------------------
# Feedback moderation
# ---------------------------------------------------------------------------
@router.get("/feedback")
async def list_feedback(admin: dict = Depends(_require_admin)) -> list[dict]:
    db = get_db()
    return (
        await db.feedback.find({}, {"_id": 0, "ip_hash": 0})
        .sort("created_at", -1)
        .to_list(500)
    )


@router.patch("/feedback/{feedback_id}")
async def moderate_feedback(
    feedback_id: str, payload: dict, admin: dict = Depends(_require_admin)
) -> dict:
    """Approve or unapprove: body is {"is_public": true|false}."""
    is_public = bool((payload or {}).get("is_public", False))
    db = get_db()
    res = await db.feedback.update_one({"id": feedback_id}, {"$set": {"is_public": is_public}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"ok": True, "id": feedback_id, "is_public": is_public}


@router.delete("/feedback/{feedback_id}")
async def delete_feedback(feedback_id: str, admin: dict = Depends(_require_admin)) -> dict:
    db = get_db()
    res = await db.feedback.delete_one({"id": feedback_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Site settings — landing-page section toggles
# ---------------------------------------------------------------------------
# One document in `settings` (id="site"). Every section defaults to ON, so a
# missing document or a newly added section never blanks the landing page.
LANDING_SECTIONS: dict[str, str] = {
    "videos": "10-second video reel",
    "stats": "Live counters (scans / recovered / visitors)",
    "how": "How it works",
    "usecases": "Where to use it",
    "features": "What you get",
    "products": "Get tags (sticker cards)",
    "sponsor": "Sponsor a tag",
    "faq": "FAQs",
    "band": "WhatsApp CTA band",
    "feedback": "Feedback & testimonials",
}


async def get_site_settings(db) -> dict:
    doc = await db.settings.find_one({"id": "site"}, {"_id": 0}) or {}
    stored = doc.get("landing_sections", {})
    return {"landing_sections": {k: bool(stored.get(k, True)) for k in LANDING_SECTIONS}}


@router.get("/settings")
async def read_settings(admin: dict = Depends(_require_admin)) -> dict:
    settings = await get_site_settings(get_db())
    settings["section_labels"] = LANDING_SECTIONS
    return settings


@router.patch("/settings")
async def update_settings(payload: dict, admin: dict = Depends(_require_admin)) -> dict:
    sections = (payload or {}).get("landing_sections") or {}
    updates = {f"landing_sections.{k}": bool(v) for k, v in sections.items() if k in LANDING_SECTIONS}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid section flags in payload")
    db = get_db()
    await db.settings.update_one({"id": "site"}, {"$set": updates}, upsert=True)
    return await get_site_settings(db)


# ---------------------------------------------------------------------------
# WhatsApp diagnostics — see WHY messages aren't going out
# ---------------------------------------------------------------------------
@router.get("/whatsapp/health")
async def whatsapp_health(admin: dict = Depends(_require_admin)) -> dict:
    """Config presence + a live token/number check against Meta (no send)."""
    return {"config": whatsapp_config_status(), "probe": whatsapp_probe()}


@router.post("/whatsapp/test")
async def whatsapp_test(payload: dict, admin: dict = Depends(_require_admin)) -> dict:
    """Send a real test message and return Meta's exact response.

    Meta's response is the diagnostic: e.g. code 131047 = the recipient hasn't
    messaged you in the last 24h (open the window first), 190 = expired token,
    131030 = recipient not in the test-mode allowlist.
    """
    to = (payload or {}).get("to", "")
    if not to:
        raise HTTPException(status_code=400, detail='Provide a recipient number, e.g. {"to": "+919876543210"}')
    return whatsapp_send_debug(to, "✅ Info-Tag test — if you got this, WhatsApp alerts are working!")


# ---------------------------------------------------------------------------
# Sponsor intents (the data was already collected — now it's viewable)
# ---------------------------------------------------------------------------
@router.get("/sponsors")
async def list_sponsors(admin: dict = Depends(_require_admin)) -> list[dict]:
    db = get_db()
    return (
        await db.sponsors.find({}, {"_id": 0, "ip_hash": 0})
        .sort("created_at", -1)
        .to_list(500)
    )
