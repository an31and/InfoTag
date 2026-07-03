"""Info-Tag — FastAPI entrypoint."""
from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging  # noqa: E402
import os  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from db import close_db, ensure_indexes, get_db, seed_admin_and_demo  # noqa: E402
from notifications import (  # noqa: E402
    email_enabled,
    masked_call_enabled,
    sms_enabled,
    twilio_enabled,
    whatsapp_enabled,
)
from routes.admin_routes import router as admin_router  # noqa: E402
from routes.auth_routes import router as auth_router  # noqa: E402
from push import push_enabled  # noqa: E402
from routes.contact_routes import router as contact_router  # noqa: E402
from routes.push_routes import router as push_router  # noqa: E402
from routes.finder_ssr import router as finder_ssr_router  # noqa: E402
from routes.message_routes import router as message_router  # noqa: E402
from routes.pdf_routes import router as pdf_router  # noqa: E402
from routes.profile_routes import router as profile_router  # noqa: E402
from routes.public_routes import router as public_router  # noqa: E402
from routes.sponsor_routes import router as sponsor_router  # noqa: E402
from routes.tag_routes import router as tag_router  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    await ensure_indexes(db)
    await seed_admin_and_demo(db)
    logger.info(
        "Info-Tag API ready. Email=%s WhatsApp=%s Twilio=%s",
        email_enabled(), whatsapp_enabled(), twilio_enabled(),
    )
    yield
    await close_db()


app = FastAPI(
    title="Info-Tag",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def _allowed_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*")
    if raw == "*":
        return [os.environ.get("FRONTEND_URL", "http://localhost:3000")]
    return [o.strip() for o in raw.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(contact_router)
app.include_router(push_router)
app.include_router(public_router)
app.include_router(tag_router)
app.include_router(profile_router)
app.include_router(message_router)
app.include_router(pdf_router)
app.include_router(sponsor_router)
app.include_router(finder_ssr_router)


@app.get("/api")
async def root() -> dict:
    return {"name": "Info-Tag API", "tagline": "Privacy-first, no-app, public-service smart tags.", "made_in": "India", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "email_enabled": email_enabled(), "whatsapp_enabled": whatsapp_enabled(), "twilio_enabled": twilio_enabled()}


@app.get("/api/features")
async def features() -> dict:
    """Which alert/contact channels this deployment has configured.

    Everything degrades gracefully: with zero providers configured the app
    still works (email off, WhatsApp/SMS off, masked calls fall back to the
    free callback-request relay; direct-mode tags use tel:/sms:/wa.me deep
    links which never need a provider).
    """
    return {
        "email": email_enabled(),
        "whatsapp": whatsapp_enabled(),
        "sms": sms_enabled(),
        "twilio": twilio_enabled(),
        "masked_calls": masked_call_enabled(),
        "web_push": push_enabled(),
        "callback_relay": True,  # always free
        "direct_deep_links": True,  # always free
        "made_in_india": True,
    }
