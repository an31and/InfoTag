"""Recovery tracking — an honest "item found" signal from inside the system.

The owner ↔ finder conversation happens outside our servers (calls, WhatsApp
deep links, callbacks), so we can't observe a hand-back directly.  Instead we
track each *incident* as a case in the ``recoveries`` collection and only
count it as recovered when the **owner** says so.

Lifecycle (``status``)
----------------------
    scanned ──finder acts──▶ finder_contacted ──prompt sent──▶ awaiting_owner
                                                                  │
         ┌──────────── owner "yes, found" ◀───────────────────────┤
         ▼                                                        │ owner "not yet"
    owner_confirmed_found   owner_not_found ◀── owner "no" ───────┤ (stays awaiting,
    (resolved_at set)                                             │  reminder re-armed)
                                                                  ▼
                       reminder 1 → final reminder → probable_unconfirmed

* Only ``owner_confirmed_found`` sets ``resolved_at``; nothing else is ever
  counted as a recovery.  ``probable_unconfirmed`` is reported separately and
  is never added to the confirmed number.
* A late owner answer still counts: a ``probable_unconfirmed`` or
  ``owner_not_found`` case can move to ``owner_confirmed_found`` from the
  dashboard (or a still-valid link).

Privacy
-------
Case documents and their events hold **no** finder data — no IP (raw or
hashed), no name, phone, message body or location.  Scan de-duplication keeps
using the existing hashed-IP ``scans`` collection; we only reference it.

Background work (free Render tier)
----------------------------------
There is no worker process.  ``run_recovery_sweeper`` is a tiny asyncio loop
started from the FastAPI lifespan.  Every pending action is stored on the case
as ``next_action_at`` (a timestamp), so the sweep is *stateless* and
idempotent: whatever is due gets done, whenever the process happens to be
awake.  On a cold start (Render free instances sleep after ~15 min idle) the
lifespan runs one sweep immediately, so reminders that fell due while asleep
go out within seconds of the next request waking the service.  Each action is
claimed with a conditional update before any message is sent, so two
instances (or an overlapping sweep) can never double-send.  Because the next
deadline is computed from when a reminder was *actually* sent, a long sleep
delays the schedule but never bursts several reminders at once.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from notifications import notify_owner
from push import push_owner
from urls import resolve_site_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
HIGH_PRIORITY_TYPES = {"special", "pet", "medical"}  # child/guardian, pet, medical

# Statuses
SCANNED = "scanned"
FINDER_CONTACTED = "finder_contacted"
AWAITING_OWNER = "awaiting_owner"
OWNER_CONFIRMED_FOUND = "owner_confirmed_found"
OWNER_NOT_FOUND = "owner_not_found"
PROBABLE_UNCONFIRMED = "probable_unconfirmed"

RECOVERY_STATUSES = (
    SCANNED,
    FINDER_CONTACTED,
    AWAITING_OWNER,
    OWNER_CONFIRMED_FOUND,
    OWNER_NOT_FOUND,
    PROBABLE_UNCONFIRMED,
)
# A new scan / contact attaches to an existing case only while it is open.
OPEN_STATUSES = (SCANNED, FINDER_CONTACTED, AWAITING_OWNER)
# Cases the owner can still answer (dashboard buttons / link).
ANSWERABLE_STATUSES = (FINDER_CONTACTED, AWAITING_OWNER, PROBABLE_UNCONFIRMED, OWNER_NOT_FOUND)

ANSWERS = ("found", "not_found", "not_yet")

REMINDER_INTERVAL = timedelta(hours=60)  # 2.5 days → inside the asked 2–3 day window
MAX_REMINDERS = 2  # one reminder + one final reminder, then probable_unconfirmed
HIGH_PRIORITY_PROMPT_DELAY = timedelta(hours=2)  # urgent alert now, "safe?" ask later
SCAN_ONLY_CASE_IDLE = timedelta(days=14)  # a stale scan-only case isn't reused
TOKEN_TTL = timedelta(days=7)
SWEEP_BATCH = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_high_priority(tag: dict) -> bool:
    return tag.get("type") in HIGH_PRIORITY_TYPES


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tag_name(tag: dict) -> str:
    return tag.get("display_name") or tag.get("label") or "your tag"


async def _log_event(db, case: dict, event_type: str, at: datetime, **extra) -> None:
    """Append-only, PII-free event log (one row per scan / contact / prompt…)."""
    await db.recovery_events.insert_one(
        {
            "id": f"rev_{uuid.uuid4().hex[:12]}",
            "recovery_id": case["id"],
            "tag_id": case["tag_id"],
            "type": event_type,
            "at": at.isoformat(),
            **extra,
        }
    )


async def _open_case(db, tag_id: str) -> Optional[dict]:
    cases = (
        await db.recoveries.find({"tag_id": tag_id, "status": {"$in": list(OPEN_STATUSES)}}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(1)
    )
    return cases[0] if cases else None


def _new_case(tag: dict, now: datetime) -> dict:
    return {
        "id": f"rec_{uuid.uuid4().hex[:12]}",
        "tag_id": tag["id"],
        "owner_id": tag.get("owner_id"),
        "tag_type": tag.get("type", "general"),
        "priority": "high" if is_high_priority(tag) else "normal",
        "status": SCANNED,
        "first_scan_at": now.isoformat(),
        "last_scan_at": now.isoformat(),
        "scan_count": 0,
        "first_contact_at": None,
        "contact_count": 0,
        "urgent_alert_at": None,
        "owner_prompted_at": None,
        "reminder_count": 0,
        "last_reminder_at": None,
        "next_action_at": None,
        "owner_response": None,
        "owner_responded_at": None,
        "resolved_at": None,
        "resolution_source": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Event capture
# ---------------------------------------------------------------------------
async def record_scan(db, tag: dict, now: Optional[datetime] = None) -> Optional[dict]:
    """Called once per *recorded* scan (after the existing 30s hashed-IP dedupe).

    Unclaimed tags are ignored — there is no owner to confirm anything.
    Never raises: recovery tracking must not break the finder page.
    """
    if not tag.get("owner_id"):
        return None
    now = now or _now()
    try:
        case = await _open_case(db, tag["id"])
        if case and case["status"] == SCANNED:
            last = _parse(case.get("last_scan_at")) or now
            if now - last > SCAN_ONLY_CASE_IDLE:
                case = None  # stale scan-only case: start a fresh incident
        if case is None:
            case = _new_case(tag, now)
            await db.recoveries.insert_one(dict(case))
        await db.recoveries.update_one(
            {"id": case["id"]},
            {"$set": {"last_scan_at": now.isoformat(), "updated_at": now.isoformat()}, "$inc": {"scan_count": 1}},
        )
        await _log_event(db, case, "scanned", now)
        return case
    except Exception as exc:  # noqa: BLE001
        logger.warning("recovery.record_scan failed: %s", exc)
        return None


async def record_finder_contact(
    db, tag: dict, action_type: str, request=None, now: Optional[datetime] = None
) -> Optional[dict]:
    """A finder sent a message / asked for a call → finder_contacted.

    * First contact of a case stamps ``first_contact_at``.
    * High-priority tags (child / pet / medical) trigger an immediate urgent
      alert on every channel, and the "found safe?" prompt is scheduled for
      later (sent by the sweeper).
    * Normal tags get the 3-option confirmation prompt right away.
    Never raises.
    """
    if not tag.get("owner_id"):
        return None
    now = now or _now()
    try:
        case = await _open_case(db, tag["id"])
        if case is None:
            case = _new_case(tag, now)
            await db.recoveries.insert_one(dict(case))

        await _log_event(db, case, "finder_contacted", now, action_type=action_type)
        if case["status"] != SCANNED:
            # Already contacted — just count it; never re-spam the owner.
            await db.recoveries.update_one(
                {"id": case["id"]}, {"$inc": {"contact_count": 1}, "$set": {"updated_at": now.isoformat()}}
            )
            return await db.recoveries.find_one({"id": case["id"]}, {"_id": 0})

        high = case.get("priority") == "high"
        site = resolve_site_url(request)
        update = {
            # Remembered so background reminders can build absolute links even
            # when SITE_URL isn't configured (no request in the sweeper).
            "site_url": site,
            "status": FINDER_CONTACTED,
            "first_contact_at": now.isoformat(),
            "updated_at": now.isoformat(),
            # High priority: ask "found safe?" later via the sweeper.
            "next_action_at": (now + HIGH_PRIORITY_PROMPT_DELAY).isoformat() if high else None,
        }
        res = await db.recoveries.update_one(
            {"id": case["id"], "status": SCANNED}, {"$set": update, "$inc": {"contact_count": 1}}
        )
        if res.modified_count == 0:  # lost a race with a parallel contact
            return await db.recoveries.find_one({"id": case["id"]}, {"_id": 0})
        case.update(update)

        owner = await db.users.find_one({"id": tag["owner_id"]}, {"_id": 0})
        if high:
            await _send_urgent_alert(db, owner, tag, case, now)
        else:
            await _send_prompt(db, owner, tag, case, kind="prompt", now=now, site=site)
        return await db.recoveries.find_one({"id": case["id"]}, {"_id": 0})
    except Exception as exc:  # noqa: BLE001
        logger.warning("recovery.record_finder_contact failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Owner messaging
# ---------------------------------------------------------------------------
async def issue_token(db, case: dict, now: Optional[datetime] = None) -> str:
    """Random 256-bit token; only its SHA-256 is stored."""
    now = now or _now()
    token = secrets.token_urlsafe(32)
    await db.recovery_tokens.insert_one(
        {
            "token_hash": _hash_token(token),
            "recovery_id": case["id"],
            "created_at": now.isoformat(),
            "expires_at": (now + TOKEN_TTL).isoformat(),
            "used_at": None,
            # BSON date so Mongo's TTL monitor can purge old rows.
            "purge_at": now + TOKEN_TTL + timedelta(days=30),
        }
    )
    return token


def confirm_link(site: str, token: str) -> str:
    # Token rides in the URL *fragment*: browsers never send it to servers,
    # so it can't leak into access logs or Referer headers.
    return f"{site}/recovery/confirm#t={token}"


def _prompt_text(tag: dict, link: str, kind: str, high: bool) -> tuple[str, str]:
    name = _tag_name(tag)
    if high:
        q_hi, q_en = "क्या वे सुरक्षित मिल गए?", "Have they been found safe?"
    else:
        q_hi, q_en = "क्या आपका सामान वापस मिल गया?", "Did you get your item back?"
    prefix = {"prompt": "", "reminder": "रिमाइंडर / Reminder: ", "final": "आख़िरी रिमाइंडर / Final reminder: "}[kind]
    subject = f"[Info-Tag] {prefix}{q_en}"
    body = (
        f"{q_hi}\n{q_en}\n\n"
        f"टैग / Tag: {name}\n\n"
        "एक क्लिक में बताएँ (लॉगिन ज़रूरी नहीं) / Answer in one tap (no login needed):\n"
        f"{link}\n\n"
        "• हाँ, मिल गया / Yes, found\n"
        "• नहीं मिला / Not found\n"
        "• अभी नहीं / Not yet\n\n"
        "यह लिंक 7 दिन तक और एक बार ही काम करेगा। आप डैशबोर्ड से भी जवाब दे सकते हैं।\n"
        "This link works once and expires in 7 days. You can also answer from your dashboard.\n"
    )
    return subject, body


async def _dispatch(owner: Optional[dict], subject: str, body: str, urgent: bool = False) -> dict:
    # notify_owner does blocking HTTP — keep it off the event loop.
    return await asyncio.to_thread(notify_owner, owner, subject, body, urgent)


async def _send_prompt(db, owner, tag, case, *, kind: str, now: datetime, site: str = "") -> None:
    if not owner:
        return
    token = await issue_token(db, case, now)
    link = confirm_link(site or resolve_site_url(None), token)
    subject, body = _prompt_text(tag, link, kind, case.get("priority") == "high")
    results = await _dispatch(owner, subject, body)
    await push_owner(db, owner["id"], subject.replace("[Info-Tag] ", "Info-Tag · "), _tag_name(tag), "/dashboard")
    if kind == "prompt":
        await db.recoveries.update_one(
            {"id": case["id"]},
            {
                "$set": {
                    "status": AWAITING_OWNER,
                    "owner_prompted_at": now.isoformat(),
                    "next_action_at": (now + REMINDER_INTERVAL).isoformat(),
                    "updated_at": now.isoformat(),
                }
            },
        )
    await _log_event(db, case, "owner_prompted" if kind == "prompt" else "reminder_sent", now, kind=kind,
                     channels=[k for k, v in (results or {}).items() if v])


async def _send_urgent_alert(db, owner, tag, case, now: datetime) -> None:
    if not owner:
        return
    name = _tag_name(tag)
    kind_hi = {"special": "आपके परिजन", "pet": "आपके पालतू", "medical": "मेडिकल टैग"}.get(tag.get("type"), "आपका टैग")
    subject = f"🚨 [Info-Tag] URGENT — someone found {name}"
    body = (
        f"🚨 तुरंत ध्यान दें: किसी ने {kind_hi} ({name}) का टैग स्कैन करके संपर्क किया है।\n"
        f"URGENT: a finder has just reached out about {name}.\n\n"
        "अपना इनबॉक्स अभी देखें / Check your Info-Tag inbox now.\n"
        "बाद में हम पूछेंगे कि क्या वे सुरक्षित मिल गए। / We'll ask you later to confirm they're safe.\n"
    )
    results = await _dispatch(owner, subject, body, urgent=True)
    await push_owner(db, owner["id"], f"🚨 Info-Tag · URGENT: {name}", "A finder reached out — open your inbox now.", "/inbox")
    await db.recoveries.update_one({"id": case["id"]}, {"$set": {"urgent_alert_at": now.isoformat()}})
    await _log_event(db, case, "urgent_alert_sent", now, channels=[k for k, v in (results or {}).items() if v])


# ---------------------------------------------------------------------------
# Owner response
# ---------------------------------------------------------------------------
class RecoveryError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def check_answerable(case: dict) -> None:
    if case["status"] == OWNER_CONFIRMED_FOUND:
        raise RecoveryError(409, "Already confirmed as found")
    if case["status"] not in ANSWERABLE_STATUSES:
        raise RecoveryError(409, "Nothing to confirm yet — no finder has contacted you about this tag")


async def apply_owner_response(db, case: dict, answer: str, source: str, now: Optional[datetime] = None) -> dict:
    """The ONLY place a case can become owner_confirmed_found."""
    if answer not in ANSWERS:
        raise RecoveryError(400, "Invalid answer")
    check_answerable(case)
    now = now or _now()
    update: dict = {
        "owner_response": answer,
        "owner_responded_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    if answer == "found":
        update.update(
            status=OWNER_CONFIRMED_FOUND,
            resolved_at=now.isoformat(),
            resolution_source=source,
            next_action_at=None,
        )
    elif answer == "not_found":
        update.update(status=OWNER_NOT_FOUND, resolution_source=source, next_action_at=None)
    else:  # not_yet → keep waiting; re-arm the next reminder / probable check
        update.update(status=AWAITING_OWNER, next_action_at=(now + REMINDER_INTERVAL).isoformat())
        if not case.get("owner_prompted_at"):
            update["owner_prompted_at"] = now.isoformat()

    res = await db.recoveries.update_one({"id": case["id"], "status": case["status"]}, {"$set": update})
    if res.matched_count == 0:
        raise RecoveryError(409, "This case changed meanwhile — please reload")
    if answer in ("found", "not_found"):
        # Close every outstanding link for this case.
        await db.recovery_tokens.update_many(
            {"recovery_id": case["id"], "used_at": None}, {"$set": {"used_at": now.isoformat()}}
        )
    await _log_event(db, case, "owner_response", now, answer=answer, source=source)
    return await db.recoveries.find_one({"id": case["id"]}, {"_id": 0})


async def consume_token(db, token: str, now: Optional[datetime] = None) -> dict:
    """Atomically mark a link token used.  Returns the token row."""
    now = now or _now()
    row = await lookup_token(db, token, now)
    claimed = await db.recovery_tokens.find_one_and_update(
        {"token_hash": row["token_hash"], "used_at": None},
        {"$set": {"used_at": now.isoformat()}},
    )
    if claimed is None:
        raise RecoveryError(409, "This link has already been used")
    return row


async def lookup_token(db, token: str, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    if not token or len(token) > 200:
        raise RecoveryError(404, "Invalid link")
    row = await db.recovery_tokens.find_one({"token_hash": _hash_token(token)}, {"_id": 0})
    if not row:
        raise RecoveryError(404, "Invalid link")
    if row.get("used_at"):
        raise RecoveryError(409, "This link has already been used")
    exp = _parse(row.get("expires_at"))
    if exp is None or exp <= now:
        raise RecoveryError(410, "This link has expired — please answer from your dashboard")
    return row


# ---------------------------------------------------------------------------
# Sweeper — reminders, delayed high-priority prompts, probable_unconfirmed
# ---------------------------------------------------------------------------
async def sweep_due(db, now: Optional[datetime] = None, site: str = "") -> dict:
    """Process every case whose ``next_action_at`` is due.  Idempotent."""
    now = now or _now()
    done = {"prompts": 0, "reminders": 0, "probable": 0}
    due = (
        await db.recoveries.find(
            {"status": {"$in": [FINDER_CONTACTED, AWAITING_OWNER]}, "next_action_at": {"$ne": None, "$lte": now.isoformat()}},
            {"_id": 0},
        )
        .sort("next_action_at", 1)
        .to_list(SWEEP_BATCH)
    )
    for case in due:
        try:
            await _process_due_case(db, case, now, site, done)
        except Exception as exc:  # noqa: BLE001 — one bad case must not stop the sweep
            logger.warning("recovery sweep failed for %s: %s", case.get("id"), exc)
    return done


async def _claim(db, case: dict, update: dict, inc: Optional[dict] = None) -> bool:
    """Conditional update on the exact state we read — guarantees one sender."""
    flt = {
        "id": case["id"],
        "status": case["status"],
        "reminder_count": case.get("reminder_count", 0),
        "next_action_at": case.get("next_action_at"),
    }
    op: dict = {"$set": update}
    if inc:
        op["$inc"] = inc
    res = await db.recoveries.update_one(flt, op)
    return res.modified_count == 1


async def _process_due_case(db, case: dict, now: datetime, site: str, done: dict) -> None:
    tag = await db.tags.find_one({"id": case["tag_id"]}, {"_id": 0})
    if not tag or not tag.get("owner_id"):
        await _claim(db, case, {"next_action_at": None, "updated_at": now.isoformat()})
        return
    owner = await db.users.find_one({"id": tag["owner_id"]}, {"_id": 0})
    site = site or resolve_site_url(None) or case.get("site_url", "")

    if case["status"] == FINDER_CONTACTED:
        # Delayed "found safe?" prompt (high priority) — claim, then send.
        if await _claim(db, case, {"next_action_at": (now + REMINDER_INTERVAL).isoformat(), "updated_at": now.isoformat()}):
            case["next_action_at"] = (now + REMINDER_INTERVAL).isoformat()
            await _send_prompt(db, owner, tag, case, kind="prompt", now=now, site=site)
            done["prompts"] += 1
        return

    count = case.get("reminder_count", 0)
    if count < MAX_REMINDERS:
        kind = "final" if count + 1 == MAX_REMINDERS else "reminder"
        if await _claim(
            db,
            case,
            {"last_reminder_at": now.isoformat(), "next_action_at": (now + REMINDER_INTERVAL).isoformat(),
             "updated_at": now.isoformat()},
            inc={"reminder_count": 1},
        ):
            await _send_prompt(db, owner, tag, case, kind=kind, now=now, site=site)
            done["reminders"] += 1
        return

    # Reminders exhausted and still no yes/no → probable, never "recovered".
    if await _claim(db, case, {"status": PROBABLE_UNCONFIRMED, "next_action_at": None, "updated_at": now.isoformat()}):
        await _log_event(db, case, "marked_probable", now)
        done["probable"] += 1


def sweep_interval_seconds() -> int:
    try:
        return max(0, int(os.environ.get("RECOVERY_SWEEP_SECONDS", "900")))
    except ValueError:
        return 900


async def run_recovery_sweeper(get_db) -> None:
    """Lightweight periodic loop started from the app lifespan.

    Runs one sweep immediately (cold-start catch-up), then every
    RECOVERY_SWEEP_SECONDS (default 900 = 15 min; 0 disables the loop but
    keeps the startup sweep).
    """
    interval = sweep_interval_seconds()
    while True:
        try:
            result = await sweep_due(get_db())
            if any(result.values()):
                logger.info("Recovery sweep: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Recovery sweep error: %s", exc)
        if interval <= 0:
            return
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Aggregates (counts only — never names, numbers or identities)
# ---------------------------------------------------------------------------
async def recovery_counts(db) -> dict:
    total_cases = await db.recoveries.count_documents({})
    contacted = await db.recoveries.count_documents({"first_contact_at": {"$ne": None}})
    confirmed = await db.recoveries.count_documents({"status": OWNER_CONFIRMED_FOUND})
    probable = await db.recoveries.count_documents({"status": PROBABLE_UNCONFIRMED})
    not_found = await db.recoveries.count_documents({"status": OWNER_NOT_FOUND})
    awaiting = await db.recoveries.count_documents({"status": {"$in": [FINDER_CONTACTED, AWAITING_OWNER]}})
    return {
        "cases_total": total_cases,
        "finder_contacts": contacted,
        "confirmed_recoveries": confirmed,
        "probable_unconfirmed": probable,
        "owner_not_found": not_found,
        "awaiting_owner": awaiting,
        # Confirmed only — probable never inflates the rate.
        "recovery_rate": round(confirmed / contacted, 4) if contacted else None,
    }


async def legacy_found_tags(db) -> int:
    """Tags an owner manually marked status='found' that have no confirmed case.

    These pre-date recovery tracking; they're still owner-set, so the public
    counter includes them — but never twice for the same tag.
    """
    confirmed_tag_ids = await db.recoveries.distinct("tag_id", {"status": OWNER_CONFIRMED_FOUND})
    return await db.tags.count_documents({"status": "found", "id": {"$nin": confirmed_tag_ids}})


async def public_recovered_count(db) -> int:
    confirmed = await db.recoveries.count_documents({"status": OWNER_CONFIRMED_FOUND})
    return confirmed + await legacy_found_tags(db)
