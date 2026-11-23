"""Offline test harness: FastAPI app + in-memory MongoDB (mongomock-motor).

Run:  cd backend && python -m pytest tests/unit -q
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("MONGO_URL", "mongodb://unused")
os.environ.setdefault("DB_NAME", "infotag_test")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ["SITE_URL"] = "https://info-tag.test"
os.environ.pop("TAG_SIGNING_KEYS", None)


@pytest_asyncio.fixture
async def db():
    from mongomock_motor import AsyncMongoMockClient

    import db as dbmod
    import event_service
    import ratelimit
    import tokens

    client = AsyncMongoMockClient()
    database = client[f"t_{uuid.uuid4().hex[:8]}"]
    dbmod._client, dbmod._db = client, database
    tokens.reset_keyring_cache()
    event_service.invalidate_caches()
    ratelimit.limiter.clear()
    ratelimit._seen.clear()
    await dbmod.ensure_indexes(database)
    yield database
    dbmod._client, dbmod._db = None, None


@pytest_asyncio.fixture
async def client(db):
    import httpx

    from server import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://info-tag.test") as c:
        yield c


async def make_user(db, email: str, role: str = "user", org_id: str | None = None, password: str = "password123") -> dict:
    from datetime import datetime, timezone

    from auth import hash_password

    doc = {
        "id": f"user_{uuid.uuid4().hex[:10]}", "email": email, "password_hash": hash_password(password),
        "display_name": email.split("@")[0], "role": role, "auth_provider": "password",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if org_id:
        doc["org_id"] = org_id
    await db.users.insert_one(dict(doc))
    return doc


async def login(client, email: str, password: str = "password123"):
    import httpx

    from server import app

    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://info-tag.test")
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def anyio_backend():
    return "asyncio"
