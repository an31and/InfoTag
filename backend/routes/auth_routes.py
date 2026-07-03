"""Auth endpoints — email/password + Emergent Google session exchange."""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth import (
    clear_auth_cookies,
    get_current_user,
    hash_ip,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from db import get_db
from models import (
    ChangePasswordPayload,
    LoginPayload,
    RegisterPayload,
    UpdateUserPayload,
    UserPublic,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _to_public_user(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "display_name": doc.get("display_name", ""),
        "phone": doc.get("phone", ""),
        "notify_on_message": doc.get("notify_on_message", True),
        "notify_on_scan": doc.get("notify_on_scan", False),
        "whatsapp_alerts": doc.get("whatsapp_alerts", False),
        "sms_alerts": doc.get("sms_alerts", False),
        "locale": doc.get("locale", "en"),
        "auth_provider": doc.get("auth_provider", "password"),
        "role": doc.get("role", "user"),
        "created_at": doc.get("created_at", datetime.now(timezone.utc).isoformat()),
    }


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


@router.post("/register", response_model=UserPublic)
async def register(payload: RegisterPayload, response: Response, request: Request) -> dict:
    db = get_db()
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": user_id,
        "email": email,
        "password_hash": hash_password(payload.password),
        "display_name": payload.display_name or email.split("@")[0],
        "notify_on_message": True,
        "notify_on_scan": False,
        "locale": "en",
        "auth_provider": "password",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    set_auth_cookies(response, user_id, email)
    return _to_public_user(doc)


@router.post("/login", response_model=UserPublic)
async def login(payload: LoginPayload, response: Response, request: Request) -> dict:
    db = get_db()
    email = payload.email.lower()
    ip = request.client.host if request.client else "0.0.0.0"
    identifier = f"{hash_ip(ip)}:{email}"

    # Brute force protection
    attempt_doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if attempt_doc and attempt_doc.get("count", 0) >= LOCKOUT_THRESHOLD:
        last_at = attempt_doc.get("last_attempt_at")
        if last_at:
            last_dt = datetime.fromisoformat(last_at) if isinstance(last_at, str) else last_at
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            if elapsed < LOCKOUT_MINUTES:
                raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {
                "$inc": {"count": 1},
                "$set": {"last_attempt_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.login_attempts.delete_one({"identifier": identifier})
    set_auth_cookies(response, user["id"], user["email"])
    return _to_public_user(user)


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(_current_user_dep)) -> dict:
    return _to_public_user(user)


@router.post("/google/session")
async def google_session(payload: dict, response: Response) -> dict:
    """Exchange Emergent Google session_id for a Info-Tag JWT cookie session.

    REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
    THIS BREAKS THE AUTH.  The frontend passes us the session_id from the URL
    fragment after Google sign-in; we exchange it server-side for the user's
    Google profile, then upsert the user and issue our own auth cookies.
    """
    session_id = (payload or {}).get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Emergent auth unreachable: {exc}")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google session")
    data = resp.json()
    email = (data.get("email") or "").lower()
    name = data.get("name") or ""
    picture = data.get("picture") or ""
    if not email:
        raise HTTPException(status_code=400, detail="Google profile missing email")

    db = get_db()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user is None:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "id": user_id,
            "email": email,
            "password_hash": "",  # Google-only — no password
            "display_name": name or email.split("@")[0],
            "picture": picture,
            "notify_on_message": True,
            "notify_on_scan": False,
            "locale": "en",
            "auth_provider": "google",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        # Merge — flag that they can use either method, refresh picture
        provider = user.get("auth_provider", "password")
        new_provider = "both" if provider != "google" else "google"
        await db.users.update_one(
            {"email": email},
            {"$set": {"auth_provider": new_provider, "picture": picture, "display_name": user.get("display_name") or name}},
        )
        user["auth_provider"] = new_provider
        user["picture"] = picture

    set_auth_cookies(response, user["id"], user["email"])
    return _to_public_user(user)


@router.patch("/me", response_model=UserPublic)
async def update_me(payload: UpdateUserPayload, user: dict = Depends(_current_user_dep)) -> dict:
    db = get_db()
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "phone" in update:
        # Keep digits + leading '+' only; an empty string clears the number.
        cleaned = re.sub(r"[^+\d]", "", update["phone"])
        if cleaned and len(cleaned.lstrip("+")) < 8:
            raise HTTPException(status_code=400, detail="Phone number looks too short")
        update["phone"] = cleaned
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
    refreshed = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return _to_public_user(refreshed)


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordPayload, user: dict = Depends(_current_user_dep)
) -> dict:
    db = get_db()
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if full.get("password_hash"):
        if not payload.current_password or not verify_password(payload.current_password, full["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "auth_provider": "both" if full.get("auth_provider") == "google" else full.get("auth_provider", "password")}},
    )
    return {"ok": True}


@router.delete("/me")
async def delete_me(
    response: Response,
    request: Request,
    user: dict = Depends(_current_user_dep),
) -> dict:
    """Right-to-be-forgotten: wipes user, tags, profiles, messages, scans.

    For password-auth users we require the current password in the request
    body — destructive irreversible operations need a confirmation that the
    UI alone cannot fake.  Google-only users (no password_hash) skip the check.
    """
    db = get_db()
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    if full.get("password_hash"):
        try:
            body = await request.json()
        except Exception:
            body = {}
        current_password = (body or {}).get("current_password", "")
        if not current_password or not verify_password(current_password, full["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is required to delete the account")
    tag_ids = [t["id"] async for t in db.tags.find({"owner_id": user["id"]}, {"id": 1, "_id": 0})]
    if tag_ids:
        await db.profiles.delete_many({"tag_id": {"$in": tag_ids}})
        await db.messages.delete_many({"tag_id": {"$in": tag_ids}})
        await db.scans.delete_many({"tag_id": {"$in": tag_ids}})
        await db.tags.delete_many({"owner_id": user["id"]})
    await db.users.delete_one({"id": user["id"]})
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/export")
async def export_account(user: dict = Depends(_current_user_dep)) -> dict:
    """Return the entire user's data set as JSON for portability/GDPR."""
    db = get_db()
    tags = [t async for t in db.tags.find({"owner_id": user["id"]}, {"_id": 0})]
    tag_ids = [t["id"] for t in tags]
    profiles = [p async for p in db.profiles.find({"tag_id": {"$in": tag_ids}}, {"_id": 0})]
    messages = [m async for m in db.messages.find({"tag_id": {"$in": tag_ids}}, {"_id": 0})]
    scans = [s async for s in db.scans.find({"tag_id": {"$in": tag_ids}}, {"_id": 0})]
    return {
        "user": _to_public_user(user),
        "tags": tags,
        "profiles": profiles,
        "messages": messages,
        "scans": scans,
    }
