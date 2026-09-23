"""Auth endpoints — email/password + Sign in with Google (OAuth 2.0)."""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

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
logger = logging.getLogger(__name__)

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
        "whatsapp_window_opens_at": doc.get("whatsapp_window_opens_at"),
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


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_STATE_COOKIE = "g_oauth_state"


def google_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def _google_redirect_uri(request: Request) -> str:
    """Must exactly match an "Authorized redirect URI" in Google Cloud Console."""
    explicit = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    return f"{proto}://{host}/api/auth/google/callback"


def _frontend_url(path: str) -> str:
    base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}{path}"


async def _upsert_google_user(email: str, name: str, picture: str) -> dict:
    db = get_db()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user is None:
        user = {
            "id": f"user_{uuid.uuid4().hex[:12]}",
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
        return user
    # Merge — flag that they can use either method, refresh picture
    provider = user.get("auth_provider", "password")
    new_provider = "both" if provider != "google" else "google"
    await db.users.update_one(
        {"email": email},
        {"$set": {"auth_provider": new_provider, "picture": picture, "display_name": user.get("display_name") or name}},
    )
    user["auth_provider"] = new_provider
    user["picture"] = picture
    return user


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Send the browser straight to Google's own consent screen."""
    if not google_enabled():
        return RedirectResponse(_frontend_url("/login?error=google_unavailable"), status_code=302)
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": _google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    # Lax so the cookie survives the top-level redirect back from Google.
    resp.set_cookie(
        GOOGLE_STATE_COOKIE, state, max_age=600, httponly=True, secure=True, samesite="lax", path="/api/auth/google"
    )
    return resp


@router.get("/google/callback")
async def google_callback(
    request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None
) -> RedirectResponse:
    """Exchange Google's authorization code, sign the user in, go to the dashboard."""
    fail = RedirectResponse(_frontend_url("/login?error=google"), status_code=302)
    fail.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth/google")
    expected_state = request.cookies.get(GOOGLE_STATE_COOKIE)
    if error or not code or not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return fail
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": os.environ["GOOGLE_CLIENT_ID"],
                    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                    "redirect_uri": _google_redirect_uri(request),
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.warning("Google token exchange failed: %s", token_resp.text[:200])
                return fail
            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google sign-in unreachable: %s", exc)
        return fail
    if info_resp.status_code != 200:
        return fail
    data = info_resp.json()
    email = (data.get("email") or "").lower()
    # Only trust verified emails — otherwise anyone could claim an existing account.
    if not email or not data.get("email_verified"):
        return fail

    user = await _upsert_google_user(email, data.get("name") or "", data.get("picture") or "")
    resp = RedirectResponse(_frontend_url("/dashboard"), status_code=302)
    resp.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth/google")
    set_auth_cookies(resp, user["id"], user["email"])
    return resp


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
