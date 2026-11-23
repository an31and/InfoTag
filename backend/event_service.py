"""Event Mode core: events, batches, token/code resolution, claims, counters.

Data model (see docs/EVENT_MODE.md for the full picture)
--------------------------------------------------------
organizations  {id, name, active, can_generate, max_tags_per_event, ...}
events         {id, org_id, code, name, date, venue, output_type, pack_size,
                default_contact_mode, default_lang, reward_text, message,
                help_desk_note, status, claims_open, next_serial,
                stats{generated, claimed, owners, scans, found, returned}}
batches        {bid, event_id, kid, serial_start, count, pack_size, kind,
                status, revoked_ranges}
claims         {_id: "<bid>:<pack_no>", event_id, owner_id, serials, manage_hash}
tags           (existing collection) — one row per *claimed* event tag:
               id "ev_<bid>_<serial>", slug = short code, event_id, batch_bid, serial
stats_daily    {_id: "<event_id>:<YYYY-MM-DD>", event_id, day, scans, claims, found}

Unclaimed tags have no row at all — they are verified from their signed
token.  Tags are permanent: nothing in Event Mode ever expires a tag.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

import tokens

OUTPUT_TYPES = ("sticker_sheet", "badge_cards", "guest_pack")
ITEM_TYPES = ("phone", "bag", "bottle", "other")
ITEM_LABELS = {
    "phone": ("Phone", "फ़ोन"),
    "bag": ("Bag", "बैग"),
    "bottle": ("Bottle", "बोतल"),
    "other": ("Item", "सामान"),
}
EVENT_CODE_RE = re.compile(r"^[A-Z0-9]{2,8}$")
MAX_TAGS_PER_BATCH = 1_000_000
CACHE_TTL = 60.0


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def hash_key(k: str) -> str:
    return hashlib.sha256((k or "").encode()).hexdigest()


def new_manage_key() -> str:
    return secrets.token_urlsafe(18)


def tag_id_for(bid: int, serial: int) -> str:
    return f"ev_{bid}_{serial}"


def item_label(item_type: str) -> str:
    en, hi = ITEM_LABELS.get(item_type, ITEM_LABELS["other"])
    return f"{hi} / {en}"


# ---------------------------------------------------------------------------
# Small TTL caches (single Render instance — keeps scans to ~1 DB read)
# ---------------------------------------------------------------------------
_batch_cache: dict[int, tuple[float, Optional[dict]]] = {}
_event_cache: dict[str, tuple[float, Optional[dict]]] = {}


def invalidate_caches() -> None:
    _batch_cache.clear()
    _event_cache.clear()


async def get_batch(db, bid: int) -> Optional[dict]:
    hit = _batch_cache.get(bid)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    doc = await db.batches.find_one({"bid": bid}, {"_id": 0})
    _batch_cache[bid] = (time.monotonic(), doc)
    return doc


async def get_event(db, event_id: str) -> Optional[dict]:
    hit = _event_cache.get(event_id)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    doc = await db.events.find_one({"id": event_id}, {"_id": 0})
    _event_cache[event_id] = (time.monotonic(), doc)
    return doc


async def next_seq(db, name: str) -> int:
    doc = await db.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return int(doc["seq"])


# ---------------------------------------------------------------------------
# Events & batches
# ---------------------------------------------------------------------------
def suggest_code(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    letters = "".join(w[0] for w in words).upper()[:4] or "EV"
    return (letters + datetime.now(timezone.utc).strftime("%y"))[:6]


async def unique_code(db, wanted: Optional[str], name: str) -> str:
    base = (wanted or suggest_code(name)).upper()
    if not EVENT_CODE_RE.match(base):
        raise ValueError("Event code must be 2–8 letters/digits (A–Z, 0–9)")
    if wanted:
        if await db.events.find_one({"code": base}, {"_id": 1}):
            raise ValueError(f"Event code {base} is already used")
        return base
    code = base
    n = 2
    while await db.events.find_one({"code": code}, {"_id": 1}):
        code = f"{base[:6]}{n}"
        n += 1
    return code


async def create_batch(db, event: dict, count: int, kind: str = "main") -> dict:
    """Reserve an event-wide serial range and register a signed batch."""
    if not 1 <= count <= MAX_TAGS_PER_BATCH:
        raise ValueError(f"Tag count must be between 1 and {MAX_TAGS_PER_BATCH:,}")
    pack = int(event.get("pack_size") or 1)
    if pack > 1 and count % pack:
        count += pack - count % pack  # keep packs whole
    ring = await tokens.load_keyring(db)
    upd = await db.events.find_one_and_update(
        {"id": event["id"]},
        {"$inc": {"next_serial": count, "stats.generated": count}},
        return_document=ReturnDocument.BEFORE,
    )
    start = int((upd or {}).get("next_serial", 0))
    if start + count > tokens.MAX_SERIAL:
        raise ValueError("Event serial space exhausted")
    bid = await next_seq(db, "batch_bid")
    batch = {
        "bid": bid,
        "event_id": event["id"],
        "org_id": event.get("org_id"),
        "kid": ring.active,
        "serial_start": start,
        "count": count,
        "pack_size": pack,
        "kind": kind,
        "status": "active",
        "revoked_ranges": [],
        "created_at": utcnow(),
    }
    await db.batches.insert_one(dict(batch))
    _batch_cache.pop(bid, None)
    _event_cache.pop(event["id"], None)
    return batch


async def batch_for_serial(db, event_id: str, serial: int) -> Optional[dict]:
    doc = await db.batches.find_one(
        {"event_id": event_id, "serial_start": {"$lte": serial}},
        {"_id": 0},
        sort=[("serial_start", -1)],
    )
    if doc and serial < doc["serial_start"] + doc["count"]:
        return doc
    return None


def is_revoked(batch: dict, serial: int) -> bool:
    if batch.get("status") == "revoked":
        return True
    return any(a <= serial <= b for a, b in batch.get("revoked_ranges") or [])


def pack_serials(batch: dict, serial: int) -> list[int]:
    size = int(batch.get("pack_size") or 1)
    first = batch["serial_start"] + ((serial - batch["serial_start"]) // size) * size
    return list(range(first, first + size))


def pack_no(batch: dict, serial: int) -> int:
    return (serial - batch["serial_start"]) // int(batch.get("pack_size") or 1)


# ---------------------------------------------------------------------------
# Token / code helpers
# ---------------------------------------------------------------------------
async def token_for(db, batch: dict, serial: int) -> str:
    ring = await tokens.load_keyring(db)
    return tokens.encode_token(ring.get(batch["kid"]), batch["bid"], serial)


async def code_for(db, event: dict, batch: dict, serial: int) -> str:
    ring = await tokens.load_keyring(db)
    return tokens.short_code(ring.get(batch["kid"]), event["code"], serial)


async def items_for(db, event: dict, batch: dict, serials, base_url: str) -> list[dict]:
    ring = await tokens.load_keyring(db)
    key = ring.get(batch["kid"])
    out = []
    for s in serials:
        tok = tokens.encode_token(key, batch["bid"], s)
        out.append({
            "serial": s,
            "token": tok,
            "url": tokens.qr_url(base_url, tok),
            "code": tokens.short_code(key, event["code"], s),
        })
    return out


@dataclass
class Resolved:
    event: dict
    batch: dict
    serial: int
    token: str
    code: str
    tag: Optional[dict]
    revoked: bool


async def resolve_token(db, token: str) -> Optional[Resolved]:
    parsed = tokens.parse_token(token)
    if not parsed:
        return None
    bid, serial, body, sig = parsed
    batch = await get_batch(db, bid)
    if not batch:
        return None
    ring = await tokens.load_keyring(db)
    key = ring.get(batch["kid"])
    if not key or not tokens.verify_sig(key, body, sig):
        return None
    if not batch["serial_start"] <= serial < batch["serial_start"] + batch["count"]:
        return None
    event = await get_event(db, batch["event_id"])
    if not event:
        return None
    tag = await db.tags.find_one({"id": tag_id_for(bid, serial)}, {"_id": 0})
    return Resolved(
        event=event,
        batch=batch,
        serial=serial,
        token=token.upper(),
        code=tokens.short_code(key, event["code"], serial),
        tag=tag,
        revoked=is_revoked(batch, serial),
    )


async def resolve_code(db, code: str) -> Optional[Resolved]:
    parsed = tokens.parse_code(code)
    if not parsed:
        return None
    ev_code, serial, check = parsed
    event = await db.events.find_one({"code": ev_code}, {"_id": 0})
    if not event:
        return None
    batch = await batch_for_serial(db, event["id"], serial)
    if not batch:
        return None
    ring = await tokens.load_keyring(db)
    key = ring.get(batch["kid"])
    if not key or not tokens.verify_code(key, ev_code, serial, check):
        return None
    return await resolve_token(db, tokens.encode_token(key, batch["bid"], serial))


# ---------------------------------------------------------------------------
# Counters (O(1) dashboards — never count_documents over millions of rows)
# ---------------------------------------------------------------------------
async def bump(db, event_id: str, **fields: int) -> None:
    if not fields:
        return
    await db.events.update_one({"id": event_id}, {"$inc": {f"stats.{k}": v for k, v in fields.items()}})
    day = today()
    await db.stats_daily.update_one(
        {"_id": f"{event_id}:{day}"},
        {"$inc": fields, "$setOnInsert": {"event_id": event_id, "day": day}},
        upsert=True,
    )


async def on_finder_action(db, tag: dict, action_type: str) -> None:
    """Hook called by the finder routes after a finder acts on any tag."""
    if not tag or not tag.get("event_id"):
        return
    if action_type == "found":
        await bump(db, tag["event_id"], found=1)
    else:
        await bump(db, tag["event_id"], messages=1)


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------
class AlreadyClaimed(Exception):
    pass


async def claim_pack(
    db,
    res: Resolved,
    *,
    owner_id: str,
    item_type: str,
    contact_mode: str,
    manage_key: str,
) -> list[dict]:
    """Atomically claim the pack containing ``res.serial`` → new tag rows.

    The claims ``_id`` is ``<bid>:<pack_no>`` so two simultaneous claims of
    the same sticker (or of two stickers in the same guest pack) cannot both
    succeed: the second insert hits the unique ``_id``.
    """
    from pymongo.errors import DuplicateKeyError

    event, batch = res.event, res.batch
    serials = pack_serials(batch, res.serial)
    claim_id = f"{batch['bid']}:{pack_no(batch, res.serial)}"
    now = utcnow()
    try:
        await db.claims.insert_one({
            "_id": claim_id,
            "event_id": event["id"],
            "org_id": event.get("org_id"),
            "batch_bid": batch["bid"],
            "serials": serials,
            "owner_id": owner_id,
            "manage_hash": hash_key(manage_key),
            "claimed_at": now,
        })
    except DuplicateKeyError as exc:
        raise AlreadyClaimed() from exc

    ring = await tokens.load_keyring(db)
    key = ring.get(batch["kid"])
    reward = (event.get("reward_text") or "").strip()
    message = (event.get("message") or "").strip()
    help_note = (event.get("help_desk_note") or "").strip()
    finder_msg = "\n".join(x for x in (message, help_note) if x)
    docs = []
    for s in serials:
        it = item_type if s == res.serial else "other"
        docs.append({
            "id": tag_id_for(batch["bid"], s),
            "slug": tokens.short_code(key, event["code"], s),
            "owner_id": owner_id,
            "type": "general",  # never "medical": emergency mode is off for event tags
            "label": item_label(it),
            "display_name": f"{item_label(it)} · {event['name']}"[:120],
            "message": finder_msg[:500],
            "status": "active",
            "data": {"item_type": it, "event_name": event["name"], "reward": reward},
            "public_fields": {"display_name": True, "message": True, "type": True, "reward": True},
            "contact": {"mode": contact_mode, "show_call": True, "show_whatsapp": True, "show_sms": True},
            "event_id": event["id"],
            "org_id": event.get("org_id"),
            "batch_bid": batch["bid"],
            "serial": s,
            "claim_id": claim_id,
            "scan_count": 0,
            "created_at": now,
            "updated_at": now,
            "claimed_at": now,
        })
    try:
        await db.tags.insert_many(docs, ordered=True)
    except Exception:
        await db.claims.delete_one({"_id": claim_id})
        await db.tags.delete_many({"claim_id": claim_id})
        raise
    await bump(db, event["id"], claimed=len(docs), owners=1)
    return docs


async def create_guest_owner(
    db, *, name: str, phone: str, email: str, wa_opt_in: bool, lang: str, event: dict, manage_key: str
) -> dict:
    from notifications import phone_last_digits

    doc = {
        "id": f"guest_{uuid.uuid4().hex[:12]}",
        "display_name": name,
        "phone": phone,
        "phone_digits": phone_last_digits(phone) if phone else "",
        "email": email,
        "whatsapp_opt_in": bool(wa_opt_in and phone),
        "whatsapp_window_opens_at": None,
        "notify_on_message": True,
        "locale": lang,
        "event_id": event["id"],
        "org_id": event.get("org_id"),
        "manage_hash": hash_key(manage_key),
        "consent_at": utcnow(),
        "created_at": utcnow(),
    }
    await db.guest_owners.insert_one(dict(doc))
    return doc


async def ensure_event_indexes(db) -> None:
    await db.organizations.create_index("id", unique=True)
    await db.events.create_index("id", unique=True)
    await db.events.create_index("code", unique=True)
    await db.events.create_index([("org_id", 1), ("created_at", -1)])
    await db.events.create_index([("created_at", -1), ("id", -1)])
    await db.batches.create_index("bid", unique=True)
    await db.batches.create_index([("event_id", 1), ("serial_start", -1)])
    await db.claims.create_index([("event_id", 1), ("claimed_at", -1)])
    await db.claims.create_index("owner_id")
    await db.guest_owners.create_index("id", unique=True)
    await db.guest_owners.create_index("phone_digits")
    await db.tags.create_index([("event_id", 1), ("serial", 1)], sparse=True)
    await db.stats_daily.create_index([("event_id", 1), ("day", 1)])
    await db.users.create_index("org_id", sparse=True)
