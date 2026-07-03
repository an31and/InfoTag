"""MongoDB connection + index/seed setup for Info-Tag."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from auth import hash_password, generate_slug

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        mongo_url = os.environ["MONGO_URL"]
        _client = AsyncIOMotorClient(mongo_url)
        _db = _client[os.environ["DB_NAME"]]
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.tags.create_index("slug", unique=True)
    await db.tags.create_index("owner_id")
    await db.tags.create_index("id", unique=True)
    await db.profiles.create_index("tag_id", unique=True)
    await db.scans.create_index("tag_id")
    await db.messages.create_index("tag_id")
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index(
        "last_attempt_at",
        expireAfterSeconds=60 * 60,  # auto-clean stale lockout entries after 1h
    )
    # Visitor counting: one doc per (hashed IP, day) — idempotent upserts.
    await db.visits.create_index([("ip_hash", 1), ("day", 1)], unique=True)
    await db.visits.create_index("day")
    # Feedback moderation queue
    await db.feedback.create_index("created_at")
    await db.feedback.create_index("is_public")


async def seed_admin_and_demo(db: AsyncIOMotorDatabase) -> None:
    """Create an admin account + demo tags so the app is testable on boot."""
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@info-tag.in")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    if admin_password == "admin123":
        import logging

        logging.getLogger(__name__).warning(
            "SECURITY: ADMIN_PASSWORD is unset — using the default 'admin123'. "
            "Set a strong ADMIN_PASSWORD in the environment before going live."
        )

    admin = await db.users.find_one({"email": admin_email}, {"_id": 0})
    if admin is None:
        admin_id = f"user_{uuid.uuid4().hex[:12]}"
        admin = {
            "id": admin_id,
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "display_name": "Anand Lakhera",
            "notify_on_message": True,
            "notify_on_scan": False,
            "locale": "en",
            "auth_provider": "password",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(admin)
    else:
        # Keep password in sync with .env so reset is easy in dev.
        from auth import verify_password
        if not verify_password(admin_password, admin.get("password_hash", "")):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"password_hash": hash_password(admin_password)}},
            )

    # Demo tags — only seed if owner has zero tags
    existing = await db.tags.count_documents({"owner_id": admin["id"]})
    if existing > 0:
        return

    now = datetime.now(timezone.utc).isoformat()
    demo_tags = [
        {
            "id": f"tag_{uuid.uuid4().hex[:12]}",
            "slug": generate_slug(),
            "owner_id": admin["id"],
            "type": "vehicle",
            "label": "My Bike",
            "display_name": "Royal Enfield Classic 350",
            "message": "If you see this bike parked badly or with lights on, tap below.",
            "status": "active",
            "data": {"vehicle_make_model": "Royal Enfield Classic 350", "vehicle_plate": "DL 5S AB 1234"},
            "public_fields": {
                "display_name": True,
                "message": True,
                "type": True,
                "vehicle_make_model": True,
                "vehicle_plate": False,
            },
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": f"tag_{uuid.uuid4().hex[:12]}",
            "slug": generate_slug(),
            "owner_id": admin["id"],
            "type": "pet",
            "label": "Bruno",
            "display_name": "Bruno — a friendly Indie",
            "message": "I'm a very good boy. Please scan to message my family.",
            "status": "active",
            "data": {"pet_name": "Bruno", "pet_breed": "Indie / Desi", "note": "Mild on medication"},
            "public_fields": {
                "display_name": True,
                "message": True,
                "type": True,
                "pet_name": True,
                "pet_breed": True,
                "note": True,
            },
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": f"tag_{uuid.uuid4().hex[:12]}",
            "slug": generate_slug(),
            "owner_id": admin["id"],
            "type": "medical",
            "label": "Anand — Medical ID",
            "display_name": "Anand Lakhera",
            "message": "Medical ID — please scan in an emergency.",
            "status": "active",
            "data": {},
            "public_fields": {"display_name": True, "type": True, "message": True},
            "created_at": now,
            "updated_at": now,
        },
    ]
    await db.tags.insert_many(demo_tags)

    # Attach a medical profile to the medical demo tag
    medical_tag = next(t for t in demo_tags if t["type"] == "medical")
    await db.profiles.insert_one(
        {
            "id": f"prof_{uuid.uuid4().hex[:12]}",
            "tag_id": medical_tag["id"],
            "emergency_mode": True,
            "blood_group": "O+",
            "allergies": "Penicillin",
            "chronic_conditions": "Asthma",
            "emergency_contact_name": "Family Contact",
            "emergency_contact_phone": "+91 89042 23100",
            "nearest_police_station": "Connaught Place PS, New Delhi",
            "additional_notes": "Carry inhaler. ICE: spouse first.",
            "consent_given": True,
            "last_updated": now,
        }
    )
