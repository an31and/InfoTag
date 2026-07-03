"""Sponsor a tag — civic enhancement.

A free public-service product like Info-Tag scales when companies and citizens
sponsor printed-sticker batches that get distributed for free (e.g. at
pet adoption camps, RTOs, hospitals).  This module collects sponsor
intents so we can stay zero-cost for end users.

The intent is simple: name + contact + how many tags they'd like to fund
and any message.  We do not run payments here — that's a follow-up.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import hash_ip
from db import get_db

router = APIRouter(prefix="/api/sponsors", tags=["sponsors"])

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(text: str, limit: int = 500) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()[:limit]


class SponsorIntent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    organization: str = ""
    tag_count: int = Field(ge=1, le=100_000)
    message: str = ""
    bot_check: str = ""  # honeypot


@router.post("")
async def submit_sponsor(payload: SponsorIntent, request: Request) -> dict:
    if payload.bot_check:
        return {"ok": True, "id": "blocked"}  # silently drop bots

    db = get_db()
    ip = request.client.host if request.client else "0.0.0.0"
    doc = {
        "id": f"spon_{uuid.uuid4().hex[:12]}",
        "name": _sanitize(payload.name, 120),
        "email": payload.email.lower(),
        "organization": _sanitize(payload.organization, 160),
        "tag_count": int(payload.tag_count),
        "message": _sanitize(payload.message, 1000),
        "ip_hash": hash_ip(ip),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "new",
    }
    await db.sponsors.insert_one(doc)
    return {"ok": True, "id": doc["id"]}


@router.get("/stats")
async def sponsor_stats() -> dict:
    """Public summary so the landing page can show 'X stickers funded'."""
    db = get_db()
    cursor = db.sponsors.aggregate(
        [{"$group": {"_id": None, "total": {"$sum": "$tag_count"}, "count": {"$sum": 1}}}]
    )
    rows = await cursor.to_list(1)
    if not rows:
        return {"total_pledged": 0, "sponsor_count": 0}
    row = rows[0]
    return {"total_pledged": int(row.get("total", 0)), "sponsor_count": int(row.get("count", 0))}
