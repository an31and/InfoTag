"""Finder → owner messages (anonymous) and owner inbox."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import get_current_user, hash_ip
from db import get_db
from models import MessageCreatePayload, MessageOut
from notifications import notify_owner
from push import push_owner

router = APIRouter(prefix="/api", tags=["messages"])


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(text: str) -> str:
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub("", text)
    return cleaned.strip()[:2000]


@router.post("/public/tags/{slug}/messages", response_model=MessageOut)
async def post_finder_message(
    slug: str, payload: MessageCreatePayload, request: Request
) -> dict:
    db = get_db()

    # Honeypot bot check
    if payload.bot_check:
        # Pretend success so bots can't differentiate
        return {
            "id": "blocked",
            "tag_id": "",
            "action_type": payload.action_type,
            "finder_name": "",
            "finder_contact": "",
            "body": "",
            "location": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    if not doc.get("owner_id"):
        raise HTTPException(status_code=400, detail="This tag is not yet claimed")

    # Rate-limit identical finder action within last 60s per hashed IP.
    # Use the left-most X-Forwarded-For entry (consistent with scan tracking)
    # so the limit still works behind nginx / a PaaS load balancer.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "0.0.0.0"
    ip_h = hash_ip(ip)
    recent = await db.messages.find_one(
        {
            "tag_id": doc["id"],
            "ip_hash": ip_h,
            "action_type": payload.action_type,
            "created_at": {"$gte": datetime.now(timezone.utc).isoformat()[:10]},  # today only, coarse
        },
        sort=[("created_at", -1)],
    )
    if recent:
        try:
            last_dt = datetime.fromisoformat(recent["created_at"])
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            if elapsed < 30:
                raise HTTPException(status_code=429, detail="Please wait a moment before sending again.")
        except (ValueError, TypeError):
            pass

    finder_contact = _sanitize(payload.finder_contact) or _sanitize(payload.finder_phone)
    msg = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "tag_id": doc["id"],
        "action_type": payload.action_type,
        "finder_name": _sanitize(payload.finder_name),
        "finder_contact": finder_contact,
        "body": _sanitize(payload.body),
        "location": payload.location,
        "ip_hash": ip_h,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(msg)

    # Alert the owner on every channel they enabled — email + WhatsApp + SMS.
    # Each channel is env-gated and best-effort, so nothing here can fail the
    # finder's request.
    owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
    if owner and owner.get("notify_on_message", True):
        link = (
            f"Action: {payload.action_type}\n"
            f"Tag: {doc.get('display_name') or doc.get('label')}\n"
            f"Message: {msg['body']}\n"
            f"From: {msg['finder_name'] or 'anonymous'} {msg['finder_contact']}\n"
        )
        if msg.get("location"):
            link += f"Location: https://maps.google.com/?q={msg['location'].get('lat')},{msg['location'].get('lng')}\n"
        notify_owner(owner, f"[Info-Tag] {payload.action_type.replace('_', ' ')} on your tag", link)
        await push_owner(
            db, owner["id"],
            f"Info-Tag · {payload.action_type.replace('_', ' ')} 📨",
            (msg["body"] or "A finder reached out about your tag.")[:140],
        )

    return {
        "id": msg["id"],
        "tag_id": msg["tag_id"],
        "action_type": msg["action_type"],
        "finder_name": msg["finder_name"],
        "finder_contact": msg["finder_contact"],
        "body": msg["body"],
        "location": msg["location"],
        "created_at": msg["created_at"],
    }


@router.get("/tags/{tag_id}/messages", response_model=list[MessageOut])
async def list_messages(tag_id: str, user: dict = Depends(_current_user_dep)) -> list[dict]:
    db = get_db()
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    msgs = (
        await db.messages.find({"tag_id": tag_id}, {"_id": 0, "ip_hash": 0})
        .sort("created_at", -1)
        .to_list(200)
    )
    return msgs


@router.get("/inbox", response_model=list[MessageOut])
async def inbox(user: dict = Depends(_current_user_dep)) -> list[dict]:
    """All messages across all of the owner's tags, newest first."""
    db = get_db()
    tag_ids = [t["id"] async for t in db.tags.find({"owner_id": user["id"]}, {"id": 1, "_id": 0})]
    if not tag_ids:
        return []
    msgs = (
        await db.messages.find({"tag_id": {"$in": tag_ids}}, {"_id": 0, "ip_hash": 0})
        .sort("created_at", -1)
        .to_list(200)
    )
    return msgs
