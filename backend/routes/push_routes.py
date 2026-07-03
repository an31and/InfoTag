"""Web Push subscription management (owner-only) — free scan alerts."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import get_current_user
from db import get_db
from push import push_enabled, send_web_push, vapid_public_key

router = APIRouter(prefix="/api/push", tags=["push"])


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


class SubscribePayload(BaseModel):
    subscription: dict[str, Any]  # the PushSubscription.toJSON() blob


@router.get("/public-key")
async def public_key() -> dict:
    return {"enabled": push_enabled(), "public_key": vapid_public_key()}


@router.post("/subscribe")
async def subscribe(payload: SubscribePayload, request: Request, user: dict = Depends(_current_user_dep)) -> dict:
    if not push_enabled():
        raise HTTPException(status_code=503, detail="Web push is not configured on this server")
    endpoint = (payload.subscription or {}).get("endpoint", "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Invalid subscription")
    db = get_db()
    await db.push_subs.update_one(
        {"user_id": user["id"], "subscription.endpoint": endpoint},
        {
            "$setOnInsert": {"id": f"push_{uuid.uuid4().hex[:12]}", "user_id": user["id"]},
            "$set": {
                "subscription": payload.subscription,
                "user_agent": request.headers.get("user-agent", "")[:200],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        },
        upsert=True,
    )
    return {"ok": True}


@router.post("/unsubscribe")
async def unsubscribe(payload: SubscribePayload, user: dict = Depends(_current_user_dep)) -> dict:
    endpoint = (payload.subscription or {}).get("endpoint", "")
    db = get_db()
    await db.push_subs.delete_many({"user_id": user["id"], "subscription.endpoint": endpoint})
    return {"ok": True}


@router.post("/test")
async def test_push(user: dict = Depends(_current_user_dep)) -> dict:
    """Fire a test notification to all of the caller's subscriptions."""
    if not push_enabled():
        raise HTTPException(status_code=503, detail="Web push is not configured on this server")
    db = get_db()
    sent = 0
    async for sub in db.push_subs.find({"user_id": user["id"]}, {"_id": 0}):
        try:
            if send_web_push(sub.get("subscription") or {}, "Info-Tag test 🔔", "Push alerts are working!", "/dashboard"):
                sent += 1
        except LookupError:
            await db.push_subs.delete_one({"id": sub["id"]})
    return {"ok": True, "sent": sent}
