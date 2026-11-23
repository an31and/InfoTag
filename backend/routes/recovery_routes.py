"""Recovery confirmation — owner answers "found / not found / not yet".

Two ways in, same rules (``recovery.apply_owner_response``):

* **Login-free link** — ``/recovery/confirm#t=<token>`` in the SPA calls
  ``GET /api/public/recovery/{token}`` (read-only, safe for link previewers)
  and ``POST /api/public/recovery/{token}`` (consumes the one-time token).
* **Dashboard** — ``GET /api/recoveries/pending`` +
  ``POST /api/recoveries/{id}/respond`` for the signed-in owner.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import recovery as rec
from auth import get_current_user
from db import get_db

router = APIRouter(prefix="/api", tags=["recovery"])


async def _current_user_dep(request: Request) -> dict:
    return await get_current_user(request, get_db())


class RecoveryAnswerPayload(BaseModel):
    answer: Literal["found", "not_found", "not_yet"]


def _public_case_view(case: dict, tag: dict | None) -> dict:
    """Only what the owner needs to answer — no finder data at all."""
    return {
        "id": case["id"],
        "status": case["status"],
        "priority": case.get("priority", "normal"),
        "tag_type": case.get("tag_type", "general"),
        "tag_name": ((tag or {}).get("display_name") or (tag or {}).get("label") or ""),
        "tag_id": case["tag_id"],
        "first_contact_at": case.get("first_contact_at"),
        "owner_prompted_at": case.get("owner_prompted_at"),
        "reminder_count": case.get("reminder_count", 0),
        "owner_response": case.get("owner_response"),
        "resolved_at": case.get("resolved_at"),
    }


def _raise(err: rec.RecoveryError) -> None:
    raise HTTPException(status_code=err.status_code, detail=err.detail)


# ---------------------------------------------------------------------------
# Login-free, token-based (one-time, expiring)
# ---------------------------------------------------------------------------
@router.get("/public/recovery/{token}")
async def get_recovery_by_token(token: str) -> dict:
    db = get_db()
    try:
        row = await rec.lookup_token(db, token)
    except rec.RecoveryError as e:
        _raise(e)
    case = await db.recoveries.find_one({"id": row["recovery_id"]}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Invalid link")
    tag = await db.tags.find_one({"id": case["tag_id"]}, {"_id": 0})
    view = _public_case_view(case, tag)
    view["expires_at"] = row["expires_at"]
    return view


@router.post("/public/recovery/{token}")
async def answer_recovery_by_token(token: str, payload: RecoveryAnswerPayload) -> dict:
    db = get_db()
    try:
        row = await rec.lookup_token(db, token)
        case = await db.recoveries.find_one({"id": row["recovery_id"]}, {"_id": 0})
        if not case:
            raise rec.RecoveryError(404, "Invalid link")
        # Validate the transition before burning the token, so a 409
        # (e.g. already confirmed) doesn't waste it…
        rec.check_answerable(case)
        # …then claim it atomically (one-time use, even under double-clicks).
        await rec.consume_token(db, token)
        updated = await rec.apply_owner_response(db, case, payload.answer, "owner_link")
    except rec.RecoveryError as e:
        _raise(e)
    tag = await db.tags.find_one({"id": updated["tag_id"]}, {"_id": 0})
    return {"ok": True, "recovery": _public_case_view(updated, tag)}


# ---------------------------------------------------------------------------
# Owner dashboard
# ---------------------------------------------------------------------------
@router.get("/recoveries/pending")
async def pending_recoveries(user: dict = Depends(_current_user_dep)) -> list[dict]:
    db = get_db()
    cases = (
        await db.recoveries.find(
            {
                "owner_id": user["id"],
                "status": {"$in": [rec.FINDER_CONTACTED, rec.AWAITING_OWNER, rec.PROBABLE_UNCONFIRMED]},
            },
            {"_id": 0},
        )
        .sort("first_contact_at", -1)
        .to_list(50)
    )
    out = []
    for c in cases:
        tag = await db.tags.find_one({"id": c["tag_id"], "owner_id": user["id"]}, {"_id": 0})
        if tag:
            out.append(_public_case_view(c, tag))
    return out


@router.post("/recoveries/{recovery_id}/respond")
async def respond_recovery(
    recovery_id: str, payload: RecoveryAnswerPayload, user: dict = Depends(_current_user_dep)
) -> dict:
    db = get_db()
    case = await db.recoveries.find_one({"id": recovery_id}, {"_id": 0})
    # Ownership is re-checked against the tag, not just the stored owner_id.
    tag = await db.tags.find_one({"id": (case or {}).get("tag_id"), "owner_id": user["id"]}, {"_id": 0}) if case else None
    if not case or not tag:
        raise HTTPException(status_code=404, detail="Recovery case not found")
    try:
        updated = await rec.apply_owner_response(db, case, payload.answer, "owner_dashboard")
    except rec.RecoveryError as e:
        _raise(e)
    return {"ok": True, "recovery": _public_case_view(updated, tag)}
