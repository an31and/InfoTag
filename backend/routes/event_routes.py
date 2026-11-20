"""Event Mode management API — admins and organisers.

Access model
------------
* ``admin``     — every organisation and event; may create, add spares, revoke.
* ``organizer`` — only events whose ``org_id`` equals their own ``org_id``.
  Creating events / spare batches needs ``organization.can_generate``.
  Anything outside their organisation answers 404 (existence is not leaked).

All checks are server-side; the React UI only mirrors them.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import event_service as es
import print_engine as pe
from auth import get_current_user
from db import get_db
from notifications import notify_owner_background
from owners import alert_profile, load_owner
from urls import resolve_site_url, site_domain

router = APIRouter(prefix="/api/events", tags=["events"])

PAGE_MAX = 200


# ---------------------------------------------------------------------------
# Auth / scope
# ---------------------------------------------------------------------------
async def event_manager(request: Request) -> dict:
    db = get_db()
    user = await get_current_user(request, db)
    role = user.get("role")
    if role == "admin":
        user["_org"] = None
        return user
    if role == "organizer" and user.get("org_id"):
        org = await db.organizations.find_one({"id": user["org_id"]}, {"_id": 0})
        if not org or not org.get("active", True):
            raise HTTPException(status_code=403, detail="Your organisation is disabled — contact the Info-Tag admin")
        user["_org"] = org
        return user
    raise HTTPException(status_code=403, detail="Event manager access required")


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def _require_admin_role(user: dict) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Only the Info-Tag admin can do this")


async def _event_or_404(db, user: dict, event_id: str) -> dict:
    ev = await db.events.find_one({"id": event_id}, {"_id": 0})
    if not ev or (not _is_admin(user) and ev.get("org_id") != user.get("org_id")):
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


def _qr_base(request: Request) -> str:
    return os.environ.get("TAG_QR_BASE", "").strip().rstrip("/") or resolve_site_url(request)


def _public_base(request: Request) -> str:
    return resolve_site_url(request)


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------
OutputType = Literal["sticker_sheet", "badge_cards", "guest_pack"]


class EventCreate(BaseModel):
    org_id: Optional[str] = None
    name: str = Field(min_length=2, max_length=120)
    code: Optional[str] = Field(default=None, max_length=8)
    date: str = Field(default="", max_length=20)
    venue: str = Field(default="", max_length=160)
    tag_count: int = Field(ge=1, le=es.MAX_TAGS_PER_BATCH)
    output_type: OutputType = "sticker_sheet"
    default_contact_mode: Literal["masked", "direct"] = "masked"
    default_lang: Literal["hi", "en"] = "hi"
    reward_text: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=300)
    help_desk_note: str = Field(default="", max_length=160)


class EventUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    date: Optional[str] = Field(default=None, max_length=20)
    venue: Optional[str] = Field(default=None, max_length=160)
    default_contact_mode: Optional[Literal["masked", "direct"]] = None
    default_lang: Optional[Literal["hi", "en"]] = None
    reward_text: Optional[str] = Field(default=None, max_length=120)
    message: Optional[str] = Field(default=None, max_length=300)
    help_desk_note: Optional[str] = Field(default=None, max_length=160)
    status: Optional[Literal["active", "archived"]] = None
    claims_open: Optional[bool] = None


class BatchCreate(BaseModel):
    count: Optional[int] = Field(default=None, ge=1, le=es.MAX_TAGS_PER_BATCH)
    percent: Optional[float] = Field(default=None, gt=0, le=100)


class RevokePayload(BaseModel):
    from_serial: Optional[int] = Field(default=None, ge=0)
    to_serial: Optional[int] = Field(default=None, ge=0)
    reason: str = Field(default="", max_length=200)


class NotifyPayload(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ReturnedPayload(BaseModel):
    returned: bool = True


def _clean(s: Optional[str], n: int) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()[:n]


def _event_out(ev: dict, batches: Optional[list] = None) -> dict:
    out = {k: v for k, v in ev.items() if k != "_id"}
    out.setdefault("stats", {})
    for k in ("generated", "claimed", "owners", "scans", "found", "returned", "messages"):
        out["stats"].setdefault(k, 0)
    if batches is not None:
        out["batches"] = batches
    return out


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@router.get("")
async def list_events(
    user: dict = Depends(event_manager),
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    org_id: Optional[str] = None,
    include_archived: bool = False,
) -> dict:
    """Keyset pagination on (created_at, id) — never ``skip`` over big lists."""
    db = get_db()
    q: dict = {}
    if not _is_admin(user):
        q["org_id"] = user["org_id"]
    elif org_id:
        q["org_id"] = org_id
    if not include_archived:
        q["status"] = {"$ne": "archived"}
    if cursor and "|" in cursor:
        c_at, c_id = cursor.split("|", 1)
        q["$or"] = [{"created_at": {"$lt": c_at}}, {"created_at": c_at, "id": {"$lt": c_id}}]
    docs = await db.events.find(q, {"_id": 0}).sort([("created_at", -1), ("id", -1)]).to_list(limit + 1)
    more = len(docs) > limit
    docs = docs[:limit]
    orgs = {}
    for d in docs:
        if d.get("org_id") and d["org_id"] not in orgs:
            o = await db.organizations.find_one({"id": d["org_id"]}, {"_id": 0, "name": 1})
            orgs[d["org_id"]] = (o or {}).get("name", "")
        d["org_name"] = orgs.get(d.get("org_id"), "")
    next_cursor = f"{docs[-1]['created_at']}|{docs[-1]['id']}" if more and docs else None
    return {"items": [_event_out(d) for d in docs], "next_cursor": next_cursor}


@router.get("/meta")
async def events_meta(user: dict = Depends(event_manager)) -> dict:
    """What the UI may offer this user (create button, presets, org list)."""
    db = get_db()
    org = user.get("_org")
    orgs = []
    if _is_admin(user):
        orgs = await db.organizations.find({"active": True}, {"_id": 0, "id": 1, "name": 1}).to_list(500)
    return {
        "role": user.get("role"),
        "org": {"id": org["id"], "name": org["name"], "max_tags_per_event": org.get("max_tags_per_event", 5000)} if org else None,
        "can_create": _is_admin(user) or bool(org and org.get("can_generate")),
        "can_revoke": _is_admin(user),
        "orgs": orgs,
        "presets": pe.presets_public(),
        "item_types": list(es.ITEM_TYPES),
        "max_tags_per_pdf": pe.MAX_TAGS_PER_PDF,
    }


@router.post("")
async def create_event(payload: EventCreate, request: Request, user: dict = Depends(event_manager)) -> dict:
    db = get_db()
    if _is_admin(user):
        org_id = payload.org_id or None
        if org_id and not await db.organizations.find_one({"id": org_id}, {"_id": 1}):
            raise HTTPException(status_code=400, detail="Unknown organisation")
    else:
        org = user["_org"]
        if not org.get("can_generate"):
            raise HTTPException(status_code=403, detail="Ask the Info-Tag admin to generate tags for your organisation")
        if payload.tag_count > int(org.get("max_tags_per_event", 5000)):
            raise HTTPException(status_code=400, detail=f"Your organisation can create at most {org.get('max_tags_per_event')} tags per event")
        org_id = user["org_id"]
    try:
        code = await es.unique_code(db, payload.code, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ev = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "org_id": org_id,
        "code": code,
        "name": _clean(payload.name, 120),
        "date": _clean(payload.date, 20),
        "venue": _clean(payload.venue, 160),
        "output_type": payload.output_type,
        "pack_size": pe.GUEST_PACK_SIZE if payload.output_type == "guest_pack" else 1,
        "default_contact_mode": payload.default_contact_mode,
        "default_lang": payload.default_lang,
        "reward_text": _clean(payload.reward_text, 120),
        "message": _clean(payload.message, 300),
        "help_desk_note": _clean(payload.help_desk_note, 160),
        "status": "active",
        "claims_open": True,
        "next_serial": 0,
        "stats": {"generated": 0, "claimed": 0, "owners": 0, "scans": 0, "found": 0, "returned": 0, "messages": 0},
        "created_by": user["id"],
        "created_at": es.utcnow(),
    }
    await db.events.insert_one(dict(ev))
    try:
        await es.create_batch(db, ev, payload.tag_count, "main")
    except ValueError as exc:
        await db.events.delete_one({"id": ev["id"]})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await get_event(ev["id"], request, user)


@router.get("/{event_id}")
async def get_event(event_id: str, request: Request, user: dict = Depends(event_manager)) -> dict:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    batches = await db.batches.find({"event_id": event_id}, {"_id": 0}).sort("serial_start", 1).to_list(1000)
    out = _event_out(ev, batches)
    base = _public_base(request)
    out["poster_url"] = f"{base}/e/{ev['code']}"
    if ev.get("org_id"):
        o = await db.organizations.find_one({"id": ev["org_id"]}, {"_id": 0, "name": 1})
        out["org_name"] = (o or {}).get("name", "")
    return out


@router.patch("/{event_id}")
async def update_event(event_id: str, payload: EventUpdate, request: Request, user: dict = Depends(event_manager)) -> dict:
    db = get_db()
    await _event_or_404(db, user, event_id)
    update = payload.model_dump(exclude_none=True)
    limits = {"name": 120, "date": 20, "venue": 160, "reward_text": 120, "message": 300, "help_desk_note": 160}
    for k, n in limits.items():
        if k in update:
            update[k] = _clean(update[k], n)
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.events.update_one({"id": event_id}, {"$set": update})
    es.invalidate_caches()
    return await get_event(event_id, request, user)


@router.post("/{event_id}/batches")
async def add_batch(event_id: str, payload: BatchCreate, request: Request, user: dict = Depends(event_manager)) -> dict:
    """Spare tags — e.g. ``{"percent": 10}`` adds 10% of the event's tags."""
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    if not _is_admin(user) and not user["_org"].get("can_generate"):
        raise HTTPException(status_code=403, detail="Ask the Info-Tag admin for spare tags")
    count = payload.count or math.ceil(int(ev.get("stats", {}).get("generated", 0)) * (payload.percent or 10) / 100)
    if not _is_admin(user) and count > int(user["_org"].get("max_tags_per_event", 5000)):
        raise HTTPException(status_code=400, detail="Too many tags for your organisation's limit")
    try:
        batch = await es.create_batch(db, ev, max(1, count), "spare")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return batch


@router.post("/{event_id}/batches/{bid}/revoke")
async def revoke_batch(event_id: str, bid: int, payload: RevokePayload, user: dict = Depends(event_manager)) -> dict:
    """Admin-only emergency switch (e.g. a box of stickers was stolen).

    Without a range the whole batch is revoked; with ``from_serial`` /
    ``to_serial`` only that range.  Reversible via ``/restore``.
    """
    _require_admin_role(user)
    db = get_db()
    await _event_or_404(db, user, event_id)
    batch = await db.batches.find_one({"bid": bid, "event_id": event_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if payload.from_serial is None:
        await db.batches.update_one({"bid": bid}, {"$set": {"status": "revoked", "revoke_reason": _clean(payload.reason, 200)}})
    else:
        a, b = payload.from_serial, payload.to_serial if payload.to_serial is not None else payload.from_serial
        lo, hi = batch["serial_start"], batch["serial_start"] + batch["count"] - 1
        if not (lo <= a <= b <= hi):
            raise HTTPException(status_code=400, detail=f"Range must be within {lo}–{hi}")
        await db.batches.update_one({"bid": bid}, {"$push": {"revoked_ranges": [a, b]}})
    es.invalidate_caches()
    return await db.batches.find_one({"bid": bid}, {"_id": 0})


@router.post("/{event_id}/batches/{bid}/restore")
async def restore_batch(event_id: str, bid: int, user: dict = Depends(event_manager)) -> dict:
    _require_admin_role(user)
    db = get_db()
    await _event_or_404(db, user, event_id)
    res = await db.batches.update_one({"bid": bid, "event_id": event_id}, {"$set": {"status": "active", "revoked_ranges": []}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Batch not found")
    es.invalidate_caches()
    return await db.batches.find_one({"bid": bid}, {"_id": 0})


# ---------------------------------------------------------------------------
# Tags (paged by serial — unclaimed tags have no rows, so we merge)
# ---------------------------------------------------------------------------
def _tag_row(item: dict, tag: Optional[dict], batch: dict, owner: Optional[dict], base: str) -> dict:
    revoked = es.is_revoked(batch, item["serial"])
    status = "revoked" if revoked else ((tag or {}).get("event_status") or ("claimed" if tag else "unclaimed"))
    phone = (owner or {}).get("phone", "") or ""
    return {
        "serial": item["serial"],
        "code": item["code"],
        "batch_bid": batch["bid"],
        "batch_kind": batch.get("kind", "main"),
        "status": status,
        "item_type": ((tag or {}).get("data") or {}).get("item_type"),
        "scan_count": (tag or {}).get("scan_count", 0),
        "claimed_at": (tag or {}).get("claimed_at"),
        "returned_at": (tag or {}).get("returned_at"),
        "owner_name": (owner or {}).get("display_name", "") if tag else "",
        "owner_phone_hint": ("•••• " + re.sub(r"\D", "", phone)[-4:]) if phone else "",
        "owner_email_hint": (re.sub(r"(^.).*(@.*$)", r"\1•••\2", owner.get("email", "")) if owner and owner.get("email") else ""),
        "tag_url": f"{base}/t/{item['token']}",
        "digital_id_url": f"{base}/id/{item['token']}",
    }


@router.get("/{event_id}/tags")
async def list_tags(
    event_id: str,
    request: Request,
    user: dict = Depends(event_manager),
    from_serial: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=PAGE_MAX),
    status: Literal["all", "claimed"] = "all",
) -> dict:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    base = _public_base(request)
    end = int(ev.get("next_serial", 0))
    rows: list[dict] = []
    if status == "claimed":
        tags = await db.tags.find(
            {"event_id": event_id, "serial": {"$gte": from_serial}}, {"_id": 0}
        ).sort("serial", 1).to_list(limit + 1)
        more = len(tags) > limit
        for t in tags[:limit]:
            batch = await es.get_batch(db, t["batch_bid"])
            item = (await es.items_for(db, ev, batch, [t["serial"]], base))[0]
            owner = await load_owner(db, t.get("owner_id"))
            rows.append(_tag_row(item, t, batch, owner, base))
        next_from = tags[limit]["serial"] if more else None
        return {"items": rows, "next_from": next_from, "total": end}

    stop = min(end, from_serial + limit)
    serials = list(range(from_serial, stop))
    tags = {t["serial"]: t async for t in db.tags.find({"event_id": event_id, "serial": {"$gte": from_serial, "$lt": stop}}, {"_id": 0})}
    batch = None
    for s in serials:
        if not batch or not (batch["serial_start"] <= s < batch["serial_start"] + batch["count"]):
            batch = await es.batch_for_serial(db, event_id, s)
        if not batch:
            continue
        item = (await es.items_for(db, ev, batch, [s], base))[0]
        t = tags.get(s)
        owner = await load_owner(db, t.get("owner_id")) if t else None
        rows.append(_tag_row(item, t, batch, owner, base))
    return {"items": rows, "next_from": stop if stop < end else None, "total": end}


@router.get("/{event_id}/lookup")
async def lookup_code(event_id: str, request: Request, code: str, user: dict = Depends(event_manager)) -> dict:
    """Help-desk lookup: type the code from a found item."""
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    res = await es.resolve_code(db, code)
    if not res or res.event["id"] != ev["id"]:
        raise HTTPException(status_code=404, detail="No tag with that code in this event")
    base = _public_base(request)
    item = {"serial": res.serial, "code": res.code, "token": res.token}
    owner = await load_owner(db, (res.tag or {}).get("owner_id"))
    return _tag_row(item, res.tag, res.batch, owner, base)


async def _tag_by_serial(db, ev: dict, serial: int) -> dict:
    t = await db.tags.find_one({"event_id": ev["id"], "serial": serial}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="That tag has not been claimed yet")
    return t


@router.post("/{event_id}/tags/{serial}/returned")
async def mark_returned(event_id: str, serial: int, payload: ReturnedPayload, user: dict = Depends(event_manager)) -> dict:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    t = await _tag_by_serial(db, ev, serial)
    was = t.get("event_status") == "returned"
    if payload.returned and not was:
        await db.tags.update_one({"id": t["id"]}, {"$set": {"event_status": "returned", "status": "found", "returned_at": es.utcnow()}})
        await es.bump(db, ev["id"], returned=1)
    elif not payload.returned and was:
        await db.tags.update_one({"id": t["id"]}, {"$set": {"status": "active"}, "$unset": {"event_status": "", "returned_at": ""}})
        await es.bump(db, ev["id"], returned=-1)
    return {"ok": True, "serial": serial, "returned": payload.returned}


@router.post("/{event_id}/tags/{serial}/notify")
async def notify_tag_owner(event_id: str, serial: int, payload: NotifyPayload, user: dict = Depends(event_manager)) -> dict:
    """Help desk → owner relay.  The organiser never sees the owner's number."""
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    t = await _tag_by_serial(db, ev, serial)
    owner = await load_owner(db, t.get("owner_id"))
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
    body = (
        f"Event: {ev['name']}\nTag: {t['slug']} ({t.get('label', '')})\n"
        f"Message from the event help desk:\n{_clean(payload.message, 500)}\n"
    )
    notify_owner_background(alert_profile(owner), f"[Info-Tag] {ev['name']} help desk", body)
    await db.messages.insert_one({
        "id": f"msg_{uuid.uuid4().hex[:12]}", "tag_id": t["id"], "action_type": "message",
        "finder_name": "Event help desk", "finder_contact": "", "body": _clean(payload.message, 500),
        "location": None, "ip_hash": "", "created_at": es.utcnow(),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Printing — chunks of ≤250 tags rendered on demand (deterministic tokens,
# so nothing is stored and any chunk can be re-printed later)
# ---------------------------------------------------------------------------
def _layout_from_query(request: Request, mode_default: str) -> pe.Layout:
    qp = request.query_params
    num = ("page_w", "page_h", "margin_top", "margin_left", "cell_w", "cell_h", "gap_x", "gap_y", "qr_mm", "offset_x", "offset_y")
    ints = ("rows", "cols", "start_slot")
    bools = ("cut_marks", "border", "show_domain")
    overrides: dict = {"mode": qp.get("mode") or mode_default}
    try:
        for k in num:
            if qp.get(k) not in (None, ""):
                overrides[k] = float(qp[k])
        for k in ints:
            if qp.get(k) not in (None, ""):
                overrides[k] = int(qp[k])
        for k in bools:
            if qp.get(k) not in (None, ""):
                overrides[k] = qp[k].lower() in ("1", "true", "yes", "on")
        preset = qp.get("preset") or None
        if preset and pe.PRESETS.get(preset, ("", {}))[1].get("mode") != overrides["mode"]:
            preset = None  # preset of another mode → use the mode default
        return pe.build_layout(preset, **overrides)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _pdf(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, max-age=300"},
    )


@router.get("/print/presets")
async def print_presets(user: dict = Depends(event_manager)) -> list[dict]:
    return pe.presets_public()


@router.get("/print/calibration.pdf")
async def calibration_pdf(request: Request, user: dict = Depends(event_manager)) -> Response:
    lay = _layout_from_query(request, request.query_params.get("mode") or "sticker_sheet")
    return _pdf(pe.render_calibration(lay), "info-tag-calibration.pdf")


@router.get("/{event_id}/print/manifest")
async def print_manifest(
    event_id: str, user: dict = Depends(event_manager), chunk_size: int = Query(pe.MAX_TAGS_PER_PDF, ge=1, le=pe.MAX_TAGS_PER_PDF)
) -> dict:
    """Chunk list: one entry per ≤250-tag PDF, per batch (packs kept whole)."""
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    pack = int(ev.get("pack_size") or 1)
    size = max(pack, chunk_size - chunk_size % pack)
    chunks = []
    async for b in db.batches.find({"event_id": event_id}, {"_id": 0}).sort("serial_start", 1):
        s, end = b["serial_start"], b["serial_start"] + b["count"]
        while s < end:
            n = min(size, end - s)
            chunks.append({"bid": b["bid"], "kind": b.get("kind"), "status": b.get("status"), "from_serial": s, "count": n})
            s += n
    return {"pack_size": pack, "chunk_size": size, "chunks": chunks}


@router.get("/{event_id}/print.pdf")
async def print_pdf(
    event_id: str,
    request: Request,
    from_serial: int = Query(0, ge=0),
    count: int = Query(pe.MAX_TAGS_PER_PDF, ge=1, le=pe.MAX_TAGS_PER_PDF),
    user: dict = Depends(event_manager),
) -> Response:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    batch = await es.batch_for_serial(db, event_id, from_serial)
    if not batch:
        raise HTTPException(status_code=404, detail="No tags at that serial")
    lay = _layout_from_query(request, ev.get("output_type", "sticker_sheet"))
    pack = int(batch.get("pack_size") or 1)
    if lay.mode == "guest_pack" and pack != pe.GUEST_PACK_SIZE:
        raise HTTPException(status_code=400, detail="Guest-pack layout needs an event created with output type guest_pack")
    end = min(from_serial + count, batch["serial_start"] + batch["count"])
    serials = [s for s in range(from_serial, end) if not es.is_revoked(batch, s)]
    items = await es.items_for(db, ev, batch, serials, _qr_base(request))
    if lay.mode == "guest_pack":
        by_pack: dict[int, list] = {}
        for it in items:
            by_pack.setdefault(es.pack_no(batch, it["serial"]), []).append(it)
        units = [{"items": v, "name": "", "group": ""} for _, v in sorted(by_pack.items()) if len(v) == pack]
    else:
        units = items
    try:
        data = pe.render_sheet(lay, units, domain=site_domain(request), event_name=ev["name"], title=f"{ev['name']} — tags")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _pdf(data, f"{ev['code']}-{from_serial:06d}-{lay.mode}.pdf")


@router.get("/{event_id}/poster.pdf")
async def poster_pdf(event_id: str, request: Request, user: dict = Depends(event_manager)) -> Response:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    base = _qr_base(request)
    m = re.match(r"^(https?://[^/]+)$", base, re.I)
    url = f"{m.group(1).upper()}/E/{ev['code']}" if m else f"{base}/e/{ev['code']}"
    data = pe.render_poster(
        event_name=ev["name"], url=url, code=ev["code"], venue=" · ".join(x for x in (ev.get("venue"), ev.get("date")) if x),
        help_note=ev.get("help_desk_note", ""), domain=site_domain(request),
    )
    return _pdf(data, f"{ev['code']}-poster.pdf")


# ---------------------------------------------------------------------------
# Exports (streamed — constant memory for any number of tags)
# ---------------------------------------------------------------------------
def _csv_safe(v) -> str:
    """Neutralise spreadsheet formulas (CSV injection) in user-typed text."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


async def _stream_rows(db, ev: dict, base: str, include_names: bool, kind: str):
    out = io.StringIO()
    w = csv.writer(out)
    if kind == "report":
        header = ["serial", "code", "batch", "status", "item_type", "scans", "claimed_at", "returned_at"]
        if include_names:
            header.append("owner_name")
    else:
        header = ["serial", "code", "digital_id_url", "tag_url", "status"]
    w.writerow(header)
    yield out.getvalue()
    end = int(ev.get("next_serial", 0))
    step = 500
    for start in range(0, end, step):
        out.seek(0)
        out.truncate()
        stop = min(end, start + step)
        tags = {t["serial"]: t async for t in db.tags.find({"event_id": ev["id"], "serial": {"$gte": start, "$lt": stop}}, {"_id": 0})}
        batch = None
        for s in range(start, stop):
            if not batch or not (batch["serial_start"] <= s < batch["serial_start"] + batch["count"]):
                batch = await es.batch_for_serial(db, ev["id"], s)
            if not batch:
                continue
            item = (await es.items_for(db, ev, batch, [s], base))[0]
            t = tags.get(s)
            owner = await load_owner(db, t.get("owner_id")) if (t and include_names) else None
            row = _tag_row(item, t, batch, owner, base)
            if kind == "report":
                r = [s, row["code"], batch["bid"], row["status"], row["item_type"] or "", row["scan_count"], row["claimed_at"] or "", row["returned_at"] or ""]
                if include_names:
                    r.append(_csv_safe(row["owner_name"]))
            else:
                r = [s, row["code"], row["digital_id_url"], row["tag_url"], row["status"]]
            w.writerow(r)
        yield out.getvalue()


@router.get("/{event_id}/report.csv")
async def report_csv(event_id: str, request: Request, include_names: bool = False, user: dict = Depends(event_manager)) -> StreamingResponse:
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    return StreamingResponse(
        _stream_rows(db, ev, _public_base(request), include_names, "report"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{ev["code"]}-report.csv"'},
    )


@router.get("/{event_id}/digital-ids.csv")
async def digital_ids_csv(event_id: str, request: Request, user: dict = Depends(event_manager)) -> StreamingResponse:
    """One shareable Digital ID link per tag — send them on WhatsApp instead of printing."""
    db = get_db()
    ev = await _event_or_404(db, user, event_id)
    return StreamingResponse(
        _stream_rows(db, ev, _public_base(request), False, "digital"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{ev["code"]}-digital-ids.csv"'},
    )


@router.get("/{event_id}/daily")
async def event_daily(event_id: str, user: dict = Depends(event_manager), days: int = Query(30, ge=1, le=365)) -> list[dict]:
    db = get_db()
    await _event_or_404(db, user, event_id)
    rows = await db.stats_daily.find({"event_id": event_id}, {"_id": 0}).sort("day", -1).to_list(days)
    return list(reversed(rows))
