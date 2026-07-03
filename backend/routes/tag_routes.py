"""Tag CRUD + claim flow + public finder lookup."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from auth import generate_slug, get_current_user, hash_ip
from db import get_db
from models import (
    DEFAULT_CONTACT,
    DEFAULT_PUBLIC_FIELDS,
    FinderView,
    TagCreatePayload,
    TagOut,
    TagUpdatePayload,
)
from notifications import masked_call_enabled
from push import push_owner
from urls import resolve_site_url

router = APIRouter(prefix="/api", tags=["tags"])


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


def _tag_doc_to_out(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "slug": doc["slug"],
        "owner_id": doc.get("owner_id"),
        "type": doc["type"],
        "label": doc.get("label", ""),
        "display_name": doc.get("display_name", ""),
        "message": doc.get("message", ""),
        "status": doc.get("status", "active"),
        "data": doc.get("data", {}),
        "public_fields": doc.get("public_fields", dict(DEFAULT_PUBLIC_FIELDS)),
        "contact": doc.get("contact", dict(DEFAULT_CONTACT)),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Owner endpoints
# ---------------------------------------------------------------------------
@router.get("/tags", response_model=list[TagOut])
async def list_tags(user: dict = Depends(_current_user_dep)) -> list[dict]:
    db = get_db()
    docs = [d async for d in db.tags.find({"owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1)]
    return [_tag_doc_to_out(d) for d in docs]


@router.post("/tags", response_model=TagOut)
async def create_tag(payload: TagCreatePayload, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    # Generate a unique slug (loop in the off-chance of collision)
    slug = generate_slug()
    while await db.tags.find_one({"slug": slug}, {"_id": 0}):
        slug = generate_slug()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"tag_{uuid.uuid4().hex[:12]}",
        "slug": slug,
        "owner_id": user["id"],
        "type": payload.type,
        "label": payload.label,
        "display_name": payload.display_name or payload.label or f"My {payload.type}",
        "message": payload.message,
        "status": "active",
        "data": payload.data,
        "public_fields": payload.public_fields or dict(DEFAULT_PUBLIC_FIELDS),
        "contact": payload.contact.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    await db.tags.insert_one(doc)
    return _tag_doc_to_out(doc)


@router.get("/tags/{tag_id}", response_model=TagOut)
async def get_tag(tag_id: str, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    return _tag_doc_to_out(doc)


@router.patch("/tags/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: str, payload: TagUpdatePayload, user: dict = Depends(_current_user_dep)
) -> dict:
    db = get_db()
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.tags.update_one({"id": tag_id, "owner_id": user["id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tag not found")
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    return _tag_doc_to_out(doc)


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: str, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    res = await db.tags.delete_one({"id": tag_id, "owner_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.profiles.delete_many({"tag_id": tag_id})
    await db.messages.delete_many({"tag_id": tag_id})
    await db.scans.delete_many({"tag_id": tag_id})
    return {"ok": True}


@router.get("/tags/{tag_id}/qr.png")
async def tag_qr_png(
    tag_id: str,
    request: Request,
    download: bool = False,
    user: dict = Depends(_current_user_dep),
) -> StreamingResponse:
    db = get_db()
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    # Absolute URL is critical: a QR with a relative path is unopenable on
    # phones.  resolve_site_url falls back to the request origin when the
    # SITE_URL env var is missing, so QRs always work.
    url = f"{resolve_site_url(request)}/api/finder/{doc['slug']}"
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    # `inline` lets the <img> preview render; `attachment` (when ?download=1)
    # gives the browser a sensible filename for a right-click/save or a
    # programmatic download.
    disposition = "attachment" if download else "inline"
    filename = f"info-tag-{doc['slug']}-qr.png"
    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Public finder lookup
# ---------------------------------------------------------------------------
def _public_data(doc: dict) -> dict:
    """Filter the `data` blob by `public_fields` so private bits stay private."""
    public_fields = doc.get("public_fields", {})
    data = doc.get("data", {}) or {}
    out: dict = {}
    for key, value in data.items():
        if public_fields.get(key, False):
            out[key] = value
    return out


async def build_contact_block(db, doc: dict) -> dict | None:
    """What may the finder use to reach the owner?

    direct → expose the owner's phone with the channels the owner enabled
             (free: tel:/sms:/wa.me deep links, no telephony provider).
    masked → never expose the phone; offer the relay callback request and,
             when Twilio is configured, the two-way masked-call bridge.
    """
    contact = doc.get("contact") or dict(DEFAULT_CONTACT)
    if not doc.get("owner_id"):
        return None
    if contact.get("mode") == "direct":
        owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0, "phone": 1})
        phone = (owner or {}).get("phone", "")
        if not phone:
            # Direct mode without a phone on file degrades to masked relay.
            return {"mode": "masked", "callback": True, "masked_call": masked_call_enabled()}
        return {
            "mode": "direct",
            "phone": phone,
            "call": bool(contact.get("show_call", True)),
            "whatsapp": bool(contact.get("show_whatsapp", True)),
            "sms": bool(contact.get("show_sms", True)),
        }
    return {
        "mode": "masked",
        "callback": bool(contact.get("show_call", True)),
        "masked_call": masked_call_enabled() and bool(contact.get("show_call", True)),
    }


@router.get("/public/tags/{slug}", response_model=FinderView)
async def get_public_tag(slug: str, request: Request) -> dict:
    db = get_db()
    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Record the scan, de-duped within 30s per (tag_id, hashed-IP) so a
    # finder hitting refresh doesn't pollute scan counts.  We prefer the
    # left-most X-Forwarded-For entry so multiple ingress IPs from one
    # client still resolve to the same hash.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        ip = fwd.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "0.0.0.0"
    ua = request.headers.get("user-agent", "")[:200]
    ip_h = hash_ip(ip)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=30)).isoformat()
    recent_scan = await db.scans.find_one(
        {"tag_id": doc["id"], "ip_hash": ip_h, "scanned_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1},
    )
    if recent_scan is None:
        await db.scans.insert_one(
            {
                "id": f"scan_{uuid.uuid4().hex[:12]}",
                "tag_id": doc["id"],
                "scanned_at": now.isoformat(),
                "approx_location": None,
                "ip_hash": ip_h,
                "user_agent": ua,
            }
        )
        # Free Web Push scan alert (opt-in via notify_on_scan)
        if doc.get("owner_id"):
            owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
            if owner and owner.get("notify_on_scan"):
                name = doc.get("display_name") or doc.get("label") or "your tag"
                await push_owner(db, owner["id"], "Info-Tag · tag scanned 👀", f"Someone just scanned “{name}”.", "/dashboard")

    emergency = None
    if doc.get("type") == "medical":
        profile = await db.profiles.find_one({"tag_id": doc["id"]}, {"_id": 0})
        if profile and profile.get("emergency_mode") and profile.get("consent_given"):
            emergency = {
                "blood_group": profile.get("blood_group", ""),
                "allergies": profile.get("allergies", ""),
                "chronic_conditions": profile.get("chronic_conditions", ""),
                "emergency_contact_name": profile.get("emergency_contact_name", ""),
                "emergency_contact_phone": profile.get("emergency_contact_phone", ""),
                "nearest_police_station": profile.get("nearest_police_station", ""),
                "additional_notes": profile.get("additional_notes", ""),
                "last_updated": profile.get("last_updated", ""),
            }

    public_fields = doc.get("public_fields", {})
    return {
        "slug": doc["slug"],
        "type": doc["type"],
        "status": doc.get("status", "active"),
        "display_name": doc.get("display_name", "") if public_fields.get("display_name", True) else "",
        "message": doc.get("message", "") if public_fields.get("message", True) else "",
        "public_data": _public_data(doc),
        "is_unclaimed": doc.get("owner_id") is None,
        "contact": await build_contact_block(db, doc),
        "emergency": emergency,
    }


# ---------------------------------------------------------------------------
# Claim flow (only meaningful for batch-pre-generated tags)
# ---------------------------------------------------------------------------
@router.post("/public/tags/{slug}/claim", response_model=TagOut)
async def claim_tag(slug: str, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    if doc.get("owner_id"):
        raise HTTPException(status_code=400, detail="Tag is already claimed")
    update = {
        "owner_id": user["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tags.update_one({"slug": slug}, {"$set": update})
    doc.update(update)
    return _tag_doc_to_out(doc)


# ---------------------------------------------------------------------------
# Activity / scans
# ---------------------------------------------------------------------------
@router.get("/tags/{tag_id}/activity")
async def tag_activity(tag_id: str, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    doc = await db.tags.find_one({"id": tag_id, "owner_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Tag not found")
    scans = (
        await db.scans.find({"tag_id": tag_id}, {"_id": 0}).sort("scanned_at", -1).to_list(50)
    )
    scan_count = await db.scans.count_documents({"tag_id": tag_id})
    msg_count = await db.messages.count_documents({"tag_id": tag_id})
    last_scan = scans[0]["scanned_at"] if scans else None
    return {
        "tag_id": tag_id,
        "scan_count": scan_count,
        "message_count": msg_count,
        "last_scan_at": last_scan,
        "recent_scans": scans[:10],
    }
