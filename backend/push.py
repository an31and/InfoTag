"""Web Push notifications — free scan/message alerts straight to the phone.

Uses the standard Web Push protocol (VAPID), so it costs ₹0 forever:
the browser vendors (Google/Mozilla/Apple) deliver the notifications.

Env-gated like every other channel:
    VAPID_PUBLIC_KEY   — base64url public key
    VAPID_PRIVATE_KEY  — base64url private key
    VAPID_SUBJECT      — mailto: contact (default mailto:an.31and@gmail.com)

Generate keys once with:  npx web-push generate-vapid-keys
                     or:  vapid --gen   (pip install py-vapid)
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def push_enabled() -> bool:
    return bool(os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY"))


def vapid_public_key() -> str:
    return os.environ.get("VAPID_PUBLIC_KEY", "")


def send_web_push(subscription: dict, title: str, body: str, url: str = "/inbox") -> bool:
    """Send one push message.  Returns False (never raises) on any failure.

    A 404/410 from the push service means the subscription is dead and the
    caller should delete it — signalled by raising LookupError.
    """
    if not push_enabled():
        return False
    try:
        from pywebpush import WebPushException, webpush

        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:an.31and@gmail.com")},
            ttl=3600,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise LookupError("subscription expired") from exc
        logger.warning("Web push failed: %s", exc)
        return False


async def push_owner(db, user_id: str, title: str, body: str, url: str = "/inbox") -> int:
    """Push to every subscription the owner registered.  Prunes dead ones.

    Best-effort: returns how many pushes were dispatched.
    """
    if not push_enabled():
        return 0
    sent = 0
    async for sub in db.push_subs.find({"user_id": user_id}, {"_id": 0}):
        try:
            if send_web_push(sub.get("subscription") or {}, title, body, url):
                sent += 1
        except LookupError:
            await db.push_subs.delete_one({"id": sub["id"]})
    return sent
