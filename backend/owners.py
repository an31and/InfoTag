"""Owner lookup that understands both account holders and event guests.

Event Mode lets a guest claim tags in under 30 seconds *without* creating an
account.  Those owners live in ``guest_owners`` (ids start with ``guest_``)
so the ``users`` collection — with its unique e-mail index and login
semantics — stays untouched.  Every place that used to do
``db.users.find_one({"id": owner_id})`` to alert or contact an owner calls
:func:`load_owner` instead, so the existing alert pipeline (email, WhatsApp,
SMS, push, masked callback) works for guests too.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

GUEST_PREFIX = "guest_"
WHATSAPP_WINDOW_HOURS = 24


def is_guest(owner_id: Optional[str]) -> bool:
    return bool(owner_id) and owner_id.startswith(GUEST_PREFIX)


async def load_owner(db, owner_id: Optional[str], projection: Optional[dict] = None) -> Optional[dict]:
    if not owner_id:
        return None
    proj = {"_id": 0, **(projection or {})}
    coll = db.guest_owners if is_guest(owner_id) else db.users
    return await coll.find_one({"id": owner_id}, proj)


def whatsapp_window_open(owner: dict, now: Optional[datetime] = None) -> bool:
    """True while Meta's free 24h customer-service window is open."""
    opened = (owner or {}).get("whatsapp_window_opens_at")
    if not opened:
        return False
    try:
        dt = datetime.fromisoformat(opened)
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - dt < timedelta(hours=WHATSAPP_WINDOW_HOURS)


def alert_profile(owner: dict) -> dict:
    """What ``notify_owner`` should use for this owner.

    Guests only get WhatsApp while their free window is open (they opted in
    by messaging us) — never a paid template — and fall back to e-mail.
    """
    if not owner:
        return owner
    if not is_guest(owner.get("id")):
        return owner
    out = dict(owner)
    out["whatsapp_alerts"] = bool(owner.get("whatsapp_opt_in")) and whatsapp_window_open(owner)
    out["sms_alerts"] = False
    out["_free_only"] = True
    return out
