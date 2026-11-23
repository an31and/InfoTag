"""Organisations + organiser credentials (admin only).

The admin creates an organisation for each event organiser and issues one
or more *organiser* logins.  An organiser signs in on the normal /login page
and can manage **only** their organisation's events and tags — enforced on
the server in ``routes/event_routes.py``.
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from auth import hash_password
from db import get_db
from routes.admin_routes import _require_admin

router = APIRouter(prefix="/api/admin/orgs", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    contact_name: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=20)
    contact_email: str = Field(default="", max_length=160)
    can_generate: bool = False  # may organisers create events / spare tags themselves?
    max_tags_per_event: int = Field(default=5000, ge=1, le=1_000_000)


class OrgUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    contact_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone: Optional[str] = Field(default=None, max_length=20)
    contact_email: Optional[str] = Field(default=None, max_length=160)
    can_generate: Optional[bool] = None
    max_tags_per_event: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    active: Optional[bool] = None


class MemberCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(default="", max_length=120)


def _clean(s: str, n: int) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()[:n]


def _gen_password() -> str:
    # 4 groups of 4 from an unambiguous alphabet — easy to read out on a call.
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


async def _org_or_404(db, org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.get("")
async def list_orgs(admin: dict = Depends(_require_admin)) -> list[dict]:
    db = get_db()
    orgs = await db.organizations.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for o in orgs:
        o["members"] = await db.users.count_documents({"org_id": o["id"], "role": "organizer"})
        o["events"] = await db.events.count_documents({"org_id": o["id"]})
    return orgs


@router.post("")
async def create_org(payload: OrgCreate, admin: dict = Depends(_require_admin)) -> dict:
    db = get_db()
    doc = {
        "id": f"org_{uuid.uuid4().hex[:12]}",
        "name": _clean(payload.name, 120),
        "contact_name": _clean(payload.contact_name, 120),
        "contact_phone": _clean(payload.contact_phone, 20),
        "contact_email": _clean(payload.contact_email, 160),
        "can_generate": payload.can_generate,
        "max_tags_per_event": payload.max_tags_per_event,
        "active": True,
        "created_by": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.organizations.insert_one(dict(doc))
    return doc


@router.patch("/{org_id}")
async def update_org(org_id: str, payload: OrgUpdate, admin: dict = Depends(_require_admin)) -> dict:
    db = get_db()
    await _org_or_404(db, org_id)
    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.organizations.update_one({"id": org_id}, {"$set": update})
    return await _org_or_404(db, org_id)


@router.get("/{org_id}/members")
async def list_members(org_id: str, admin: dict = Depends(_require_admin)) -> list[dict]:
    db = get_db()
    await _org_or_404(db, org_id)
    return await db.users.find(
        {"org_id": org_id, "role": "organizer"},
        {"_id": 0, "id": 1, "email": 1, "display_name": 1, "created_at": 1},
    ).to_list(200)


@router.post("/{org_id}/members")
async def add_member(org_id: str, payload: MemberCreate, admin: dict = Depends(_require_admin)) -> dict:
    """Create an organiser login.  The password is returned ONCE — share it."""
    db = get_db()
    org = await _org_or_404(db, org_id)
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        if existing.get("role") == "admin":
            raise HTTPException(status_code=400, detail="That account is an admin")
        if existing.get("role") == "organizer" and existing.get("org_id") not in (None, org_id):
            raise HTTPException(status_code=400, detail="That account already manages another organisation")
        await db.users.update_one({"id": existing["id"]}, {"$set": {"role": "organizer", "org_id": org_id}})
        return {"id": existing["id"], "email": email, "org_id": org_id, "org_name": org["name"], "password": None, "linked_existing": True}

    password = _gen_password()
    user = {
        "id": f"user_{uuid.uuid4().hex[:12]}",
        "email": email,
        "password_hash": hash_password(password),
        "display_name": _clean(payload.display_name, 120) or org["name"],
        "notify_on_message": True,
        "notify_on_scan": False,
        "locale": "hi",
        "auth_provider": "password",
        "role": "organizer",
        "org_id": org_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    return {"id": user["id"], "email": email, "org_id": org_id, "org_name": org["name"], "password": password, "linked_existing": False}


@router.post("/{org_id}/members/{user_id}/reset-password")
async def reset_member_password(org_id: str, user_id: str, admin: dict = Depends(_require_admin)) -> dict:
    db = get_db()
    member = await db.users.find_one({"id": user_id, "org_id": org_id, "role": "organizer"}, {"_id": 0})
    if not member:
        raise HTTPException(status_code=404, detail="Organiser not found")
    password = _gen_password()
    await db.users.update_one({"id": user_id}, {"$set": {"password_hash": hash_password(password), "auth_provider": "password"}})
    return {"id": user_id, "email": member["email"], "password": password}


@router.delete("/{org_id}/members/{user_id}")
async def remove_member(org_id: str, user_id: str, admin: dict = Depends(_require_admin)) -> dict:
    """Revoke organiser access (the account becomes a normal user)."""
    db = get_db()
    res = await db.users.update_one(
        {"id": user_id, "org_id": org_id, "role": "organizer"},
        {"$set": {"role": "user"}, "$unset": {"org_id": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Organiser not found")
    return {"ok": True}
