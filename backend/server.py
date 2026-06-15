"""TagIT — FastAPI entrypoint."""
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
from notifications import email_enabled, twilio_enabled, whatsapp_enabled  # noqa: E402
from routes.auth_routes import router as auth_router  # noqa: E402
from routes.finder_ssr import router as finder_ssr_router  # noqa: E402
from routes.message_routes import router as message_router  # noqa: E402
from routes.pdf_routes import router as pdf_router  # noqa: E402
from routes.profile_routes import router as profile_router  # noqa: E402
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
        "TagIT API ready. Email=%s WhatsApp=%s Twilio=%s",
        email_enabled(), whatsapp_enabled(), twilio_enabled(),
    )
    yield
    await close_db()


app = FastAPI(
    title="TagIT",
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
app.include_router(tag_router)
app.include_router(profile_router)
app.include_router(message_router)
app.include_router(pdf_router)
app.include_router(sponsor_router)
app.include_router(finder_ssr_router)


@app.get("/api")
async def root() -> dict:
    return {"name": "TagIT API", "tagline": "Privacy-first, no-app, public-service smart tags.", "made_in": "India", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "email_enabled": email_enabled(), "whatsapp_enabled": whatsapp_enabled(), "twilio_enabled": twilio_enabled()}


@app.get("/api/features")
async def features() -> dict:
    return {"email": email_enabled(), "whatsapp": whatsapp_enabled(), "twilio_masked_calls": twilio_enabled(), "made_in_india": True}


@app.post("/api/integrations/whatsapp/notify")
async def whatsapp_notify_placeholder() -> dict:
    if not whatsapp_enabled():
        return {"ok": False, "reason": "WhatsApp notifications are a paid feature — configure WHATSAPP_API_KEY"}
    return {"ok": True, "note": "Wired placeholder — implement provider call here."}


@app.post("/api/integrations/twilio/connect-call")
async def twilio_connect_call_placeholder() -> dict:
    if not twilio_enabled():
        return {"ok": False, "reason": "Masked calling is a paid feature — configure TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN"}
    return {"ok": True, "note": "Wired placeholder — implement masked-call flow here."}
