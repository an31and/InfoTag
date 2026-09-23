# InfoTag — backend (FastAPI)

Async FastAPI service for the InfoTag ecosystem.

## Stack
- FastAPI + Pydantic v2
- Motor (async MongoDB driver)
- bcrypt for password hashing
- PyJWT for cookie-based auth (httpOnly, secure, samesite=none)
- `qrcode` + `reportlab` for QR + sticker PDFs

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit values
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```
Then open `http://localhost:8001/docs` for the auto-generated Swagger UI.

## Tests
```bash
pytest -q
```

## Layout
```
backend/
├── server.py              app entrypoint + lifespan
├── auth.py                JWT, bcrypt, slug generator
├── db.py                  Motor client + indexes + boot seed
├── notifications.py       email (SMTP / SendGrid) — env-gated
├── models.py              Pydantic models + types
├── routes/
│   ├── auth_routes.py     register / login / google oauth / me / export / delete
│   ├── tag_routes.py      CRUD + public finder lookup + QR PNG + claim
│   ├── profile_routes.py  medical/emergency profile
│   ├── message_routes.py  finder → owner messages + inbox
│   ├── pdf_routes.py      A4 / ID-card / keyring PDF generator
│   └── sponsor_routes.py  sponsor-a-batch civic enhancement
├── seed.py                standalone seed script
└── tests/                 pytest suite
```

## Routes overview
See the root [README](../README.md) for the full API table.
