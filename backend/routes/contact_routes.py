"""Finder → owner contact actions: callback requests and masked calls.

The mask / no-mask model
------------------------
* **direct** tags expose the owner's phone on the finder page as free
  ``tel:`` / ``sms:`` / ``wa.me`` deep links — handled entirely client-side,
  nothing to do here.
* **masked** tags never reveal the owner's number.  Two paths back:

  1. **Callback request (always available, ₹0)** — the finder leaves *their*
     number; we relay it to the owner over email/WhatsApp/SMS and the owner
     calls back.  The owner's number is never disclosed.
  2. **Masked call bridge (env-gated, Twilio)** — Twilio rings the finder and
     dials the owner with the Twilio number as caller ID, so *neither* party
     sees the other's real number.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth import hash_ip
from db import get_db
from notifications import masked_call_enabled, notify_owner, start_masked_call
from push import push_owner

router = APIRouter(prefix="/api/public/tags", tags=["contact"])

_PHONE_RE = re.compile(r"[^+\d]")


def _clean_phone(phone: str) -> str:
    cleaned = _PHONE_RE.sub("", phone or "")
    return cleaned if len(cleaned.lstrip("+")) >= 8 else ""


def _client_ip_hash(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "0.0.0.0")
    return hash_ip(ip)


class CallRequestPayload(BaseModel):
    finder_phone: str = Field(min_length=8, max_length=20)
    finder_name: str = ""
    bot_check: str = ""  # honeypot


async def _load_claimed_tag(db, slug: str) -> dict:
    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    if not doc.get("owner_id"):
        raise HTTPException(status_code=400, detail="This tag is not yet claimed")
    return doc


async def _rate_limited(db, tag_id: str, ip_h: str, action: str, seconds: int = 60) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    recent = await db.messages.find_one(
        {"tag_id": tag_id, "ip_hash": ip_h, "action_type": action, "created_at": {"$gte": cutoff}}
    )
    return recent is not None


@router.post("/{slug}/call-request")
async def request_callback(slug: str, payload: CallRequestPayload, request: Request) -> dict:
    """Free masked contact: relay the finder's number to the owner."""
    if payload.bot_check:
        return {"ok": True}  # silently drop bots

    phone = _clean_phone(payload.finder_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Please enter a valid phone number")

    db = get_db()
    doc = await _load_claimed_tag(db, slug)
    ip_h = _client_ip_hash(request)
    if await _rate_limited(db, doc["id"], ip_h, "call_request"):
        raise HTTPException(status_code=429, detail="Please wait a moment before requesting again.")

    name = re.sub(r"<[^>]+>", "", payload.finder_name or "").strip()[:120]
    msg = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "tag_id": doc["id"],
        "action_type": "call_request",
        "finder_name": name,
        "finder_contact": phone,
        "body": "Callback requested — please call this finder back.",
        "location": None,
        "ip_hash": ip_h,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(msg)

    owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
    if owner and owner.get("notify_on_message", True):
        notify_owner(
            owner,
            "[Info-Tag] Call-back request on your tag",
            (
                f"Tag: {doc.get('display_name') or doc.get('label')}\n"
                f"Finder: {name or 'anonymous'}\n"
                f"Phone: {phone}\n"
                "They are waiting near your item — please call them back.\n"
            ),
        )
        await push_owner(db, owner["id"], "Info-Tag · call-back request 📞", f"A finder left their number: {phone}. Call them back!")
    return {"ok": True, "id": msg["id"]}


@router.post("/{slug}/masked-call")
async def masked_call(slug: str, payload: CallRequestPayload, request: Request) -> dict:
    """Premium masked contact: two-way Twilio bridge, both numbers hidden."""
    if payload.bot_check:
        return {"ok": True}

    phone = _clean_phone(payload.finder_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Please enter a valid phone number")

    db = get_db()
    doc = await _load_claimed_tag(db, slug)

    if not masked_call_enabled():
        # Graceful downgrade — the UI should offer the free callback path.
        return {"ok": False, "fallback": "callback", "reason": "Masked calling is not configured"}

    owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
    owner_phone = (owner or {}).get("phone", "")
    if not owner_phone:
        return {"ok": False, "fallback": "callback", "reason": "Owner has no phone on file"}

    ip_h = _client_ip_hash(request)
    if await _rate_limited(db, doc["id"], ip_h, "call_request", seconds=120):
        raise HTTPException(status_code=429, detail="Please wait before calling again.")

    ok = start_masked_call(phone, owner_phone)
    await db.messages.insert_one(
        {
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "tag_id": doc["id"],
            "action_type": "call_request",
            "finder_name": re.sub(r"<[^>]+>", "", payload.finder_name or "").strip()[:120],
            "finder_contact": phone,
            "body": "Masked call bridged." if ok else "Masked call attempted but failed.",
            "location": None,
            "ip_hash": ip_h,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if not ok:
        return {"ok": False, "fallback": "callback", "reason": "Call could not be placed"}
    return {"ok": True}
