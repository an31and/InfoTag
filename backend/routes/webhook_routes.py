"""WhatsApp Cloud API webhook.

Two responsibilities:
  1. The GET verification handshake Meta requires when you click
     "Verify and save" on the Configure Webhooks screen.
  2. The POST event receiver — logs delivery/read/failed status updates
     (previously invisible to notify_owner(), which is fire-and-forget),
     and opens an owner's free 24h WhatsApp "customer service window"
     whenever they message the business number directly.

Env-gated like the rest of notifications.py: with no env vars set the
verification handshake always fails closed (403) rather than silently
matching on an empty token, and the POST receiver still 200s (so Meta
doesn't disable the subscription) but does nothing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from db import get_db
from notifications import phone_last_digits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["webhooks"])

VERIFY_TOKEN = os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
APP_SECRET = os.environ.get("META_APP_SECRET", "")


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> Response:
    """Meta's one-time handshake — echo hub.challenge back iff the token matches."""
    if VERIFY_TOKEN and hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, VERIFY_TOKEN):
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("WhatsApp webhook verification failed (mode=%s)", hub_mode)
    return Response(status_code=403)


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Check Meta's X-Hub-Signature-256 header, when META_APP_SECRET is set.

    Skipped (returns True) if no app secret is configured — that keeps
    local/dev testing zero-config, at the cost of not authenticating the
    sender. Set META_APP_SECRET before relying on this in production.
    """
    if not APP_SECRET:
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[len("sha256=") :])


async def _open_window_for(db: AsyncIOMotorDatabase, wa_id: str) -> bool:
    """Stamp whatsapp_window_opens_at on whichever owner this wa_id belongs to.

    Owners type their phone number free-form in Settings (spaces, +, with
    or without country code), so an exact/indexed match on the raw field
    isn't reliable — this compares the last 10 digits instead. InfoTag's
    owner base is small, so the scan below is fine; if it ever needs to
    scale, add a normalised `phone_digits` field on write + index that.
    """
    last10 = phone_last_digits(wa_id)
    if not last10:
        return False
    async for u in db.users.find({"phone": {"$nin": ["", None]}}, {"_id": 0, "id": 1, "phone": 1}):
        if phone_last_digits(u.get("phone")) == last10:
            await db.users.update_one(
                {"id": u["id"]},
                {"$set": {"whatsapp_window_opens_at": datetime.now(timezone.utc).isoformat()}},
            )
            return True
    return False


async def _event_opt_in(db: AsyncIOMotorDatabase, wa_id: str, text: str) -> str | None:
    """Event guests opt in by sending ``START <code>`` from the claim page.

    Matching on the printed code (not on a scan of every phone number) is
    exact and indexed; it also proves the guest owns that WhatsApp number.
    Any later message from a known guest number re-opens the free window.
    """
    import event_service as es
    from notifications import send_whatsapp_background

    now = datetime.now(timezone.utc).isoformat()
    m = re.match(r"^\s*START\s+([A-Za-z0-9 \-]{6,24})\s*$", text or "", re.I)
    if m:
        res = await es.resolve_code(db, m.group(1))
        owner_id = (res.tag or {}).get("owner_id") if res else None
        if owner_id and owner_id.startswith("guest_"):
            await db.guest_owners.update_one(
                {"id": owner_id},
                {"$set": {"whatsapp_opt_in": True, "whatsapp_window_opens_at": now,
                          "wa_id": wa_id, "phone_digits": phone_last_digits(wa_id)}},
            )
            send_whatsapp_background(
                wa_id,
                f"✅ Info-Tag alerts are ON for {res.code} ({res.event['name']}). "
                "If someone finds your item we'll message you here. "
                "अलर्ट चालू हैं — सामान मिलने पर हम यहीं संदेश भेजेंगे।",
            )
            return "start"
    last10 = phone_last_digits(wa_id)
    if last10:
        res2 = await db.guest_owners.update_many(
            {"phone_digits": last10, "whatsapp_opt_in": True},
            {"$set": {"whatsapp_window_opens_at": now}},
        )
        if res2.matched_count:
            return "refresh"
    return None


async def _process_payload(db: AsyncIOMotorDatabase, payload: dict) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                wa_id = msg.get("from", "")
                text = ((msg.get("text") or {}).get("body") or "").strip()
                if wa_id and await _event_opt_in(db, wa_id, text) == "start":
                    continue
                if wa_id and await _open_window_for(db, wa_id):
                    logger.info("WhatsApp window opened for wa_id=%s…", wa_id[:6])
            for status in value.get("statuses", []) or []:
                logger.info(
                    "WhatsApp status: id=%s status=%s recipient=%s",
                    status.get("id"), status.get("status"), status.get("recipient_id"),
                )


@router.post("")
async def receive_webhook(request: Request) -> dict:
    raw = await request.body()
    if not _verify_signature(raw, request.headers.get("x-hub-signature-256", "")):
        logger.warning("WhatsApp webhook: signature mismatch, ignoring payload")
        return {"status": "ignored"}
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        return {"status": "ignored"}
    try:
        await _process_payload(get_db(), payload)
    except Exception as exc:  # noqa: BLE001 — never let a parse hiccup 500 to Meta
        logger.warning("WhatsApp webhook processing failed: %s", exc)
    return {"status": "ok"}
