# Info-Tag — privacy-first, no-app smart tags

> Lose less. Help more.  

Info-Tag is a self-hostable web app + PWA that lets ordinary people stick a QR
sticker on their bike, pet's collar, luggage, keys or wallet — and lets a
kind person reach the owner if it's ever lost, **without installing an app**.

It also offers a **Medical Emergency Mode** so first responders can see blood
group, allergies and an emergency contact in seconds.

## Why

Most "smart tag" products lock finders into an app, expose owners' phone
numbers, or charge a subscription. Info-Tag does none of those.

- **No app for finders.** Any phone camera. Open web page. Done.
- **PWA for owners.** Installable on Android/iOS via the web manifest.
- **Privacy-first.** Owner's phone number is never exposed; messages route
  via server-side relays. IPs are hashed.
- **Masked or direct contact — per tag.** Competitors sell separate "mask
  calling" and "direct calling" products; Info-Tag makes it a free toggle.
  *Masked* (default): finders message you or request a call back — your
  number never appears; an optional Twilio bridge hides both numbers.
  *Direct*: finders get one-tap Call / WhatsApp / SMS buttons (free deep
  links, no telephony provider needed).
- **Multi-channel alerts.** Finder actions fan out to email (free),
  WhatsApp (Meta Cloud API free tier) and SMS (Twilio) — each env-gated
  and off until configured.
- **Medical IDs with consent.** Wrong medical data is dangerous, so accuracy
  is a first-class concern: explicit consent + last-updated date.
- **Free and open-source (MIT).** Made in India 🇮🇳.

## Architecture

```
┌──────────────────┐    HTTPS+cookies     ┌────────────────────┐
│  React PWA       │ ───────────────────▶ │  FastAPI backend   │
│  (Tailwind, SW)  │ ◀─────────────────── │  (JWT + Mongo)     │
└──────────────────┘   JSON over /api      └─────────┬──────────┘
                                                     │
                                              ┌──────▼──────┐
                                              │  MongoDB    │
                                              └─────────────┘
```

- **Backend**: FastAPI + async Motor driver + JWT cookies + bcrypt
  passwords + Pydantic v2. Auto-docs at `/docs`.
- **Frontend**: React + Tailwind + shadcn/ui, configured as a PWA.
- **Database**: MongoDB. Collections: `users`, `tags`, `profiles`,
  `scans`, `messages`, `sponsors`, `login_attempts`.
- **Email/WhatsApp/Twilio**: optional, env-gated, fully implemented —
  email via SendGrid/SMTP, WhatsApp via the Meta Cloud API, SMS and the
  two-way masked-call bridge via Twilio. All skipped silently when not
  configured.

## Run locally (one command)

```bash
cp backend/.env.example backend/.env
# edit JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, SITE_URL
docker compose up --build
```

Open `http://localhost:3000`. Sign in with the admin you set in `backend/.env`
— the backend boot-seeds it with three demo tags so you can scan immediately.

## Run without Docker

```bash
# 1. MongoDB
mongod --dbpath /tmp/infotag-db &

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit
uvicorn server:app --host 0.0.0.0 --port 8001

# 3. Frontend
cd frontend
yarn install
yarn start
```

## API quick tour

| Method | Endpoint                                | Auth       | Purpose                                  |
|-------:|-----------------------------------------|------------|------------------------------------------|
| POST   | `/api/auth/register`                    | none       | email/password signup                    |
| POST   | `/api/auth/login`                       | none       | email/password login                     |
| POST   | `/api/auth/google/session`              | none       | Exchange Emergent Google `session_id`    |
| GET    | `/api/auth/me`                          | cookie JWT | Current user                             |
| GET    | `/api/auth/export`                      | cookie JWT | Full data export (GDPR)                  |
| DELETE | `/api/auth/me`                          | cookie JWT | Right-to-be-forgotten (needs password)   |
| GET    | `/api/tags`                             | cookie JWT | List owner's tags                        |
| POST   | `/api/tags`                             | cookie JWT | Create a tag                             |
| GET    | `/api/tags/{id}/qr.png`                 | cookie JWT | QR PNG                                   |
| GET    | `/api/tags/{id}/pdf?layout=a4_stickers` | cookie JWT | Sticker PDF (a4_stickers/id_card/keyring)|
| GET    | `/api/public/tags/{slug}`               | none       | Finder view + records a scan             |
| POST   | `/api/public/tags/{slug}/messages`      | none       | Finder → owner anonymous message         |
| POST   | `/api/public/tags/{slug}/call-request`  | none       | Masked call-back request (free relay)    |
| POST   | `/api/public/tags/{slug}/masked-call`   | none       | Two-way masked call bridge (Twilio-gated)|
| POST   | `/api/sponsors`                         | none       | Pledge to sponsor printed stickers       |

Full reference: `http://localhost:8001/docs`.

## Folder layout

```
/app
├── backend/                FastAPI + MongoDB
│   ├── server.py
│   ├── auth.py             JWT + bcrypt
│   ├── db.py               Mongo client + indexes + seed
│   ├── notifications.py    Email (env-gated)
│   ├── routes/             auth, tag, profile, message, pdf, sponsor
│   ├── tests/              pytest suite (33 tests)
│   ├── seed.py             Standalone seed script
│   ├── Dockerfile
│   └── .env.example
├── frontend/               React PWA
│   ├── src/
│   │   ├── App.js
│   │   ├── lib/            auth, i18n, theme, api
│   │   ├── components/     AppShell, LanguageSwitcher, ThemeToggle
│   │   └── pages/          Landing, Auth, Dashboard, TagEdit, TagQR,
│   │                       TagMedical, Inbox, Settings, Finder, Claim, Legal
│   ├── public/             manifest.json, sw.js, index.html
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
├── LICENSE                 MIT
├── CONTRIBUTING.md
└── README.md
```

## Alert / contact providers (all optional)

The app runs fully with **zero** providers configured — email, WhatsApp and
SMS alerts each switch on when their env vars appear:

| Channel | Env vars | Cost |
|---|---|---|
| Email | `SENDGRID_API_KEY` *or* `SMTP_HOST`+`SMTP_USER`(+`SMTP_PASS`,`SMTP_PORT`,`EMAIL_FROM`) | free |
| Web Push | `VAPID_PUBLIC_KEY` + `VAPID_PRIVATE_KEY` (+`VAPID_SUBJECT`) | free forever |
| WhatsApp | `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` (Meta Cloud API) | free service tier |
| SMS + masked calls | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_FROM_NUMBER` | paid, env-gated |

Direct-mode contact buttons (tel:/wa.me/sms:) and the masked callback-request
relay never need a provider — they are free forever.

**Step-by-step setup for every channel (Gmail, SendGrid, Meta WhatsApp
Cloud API, Twilio, India DLT notes, troubleshooting):**
[`docs/ACTIVATION_GUIDE.md`](./docs/ACTIVATION_GUIDE.md)

## Roadmap

See [`docs/PRODUCT_ANALYSIS.md`](./docs/PRODUCT_ANALYSIS.md) for the full
competitive analysis (GetBackLost, EkTag, Sampark, LetzScan, LostIt) and the
ranked roadmap. Highlights:

- Phone verification (OTP) before a tag can switch to direct mode.
- Web Push scan alerts through the existing PWA service worker.
- Lost-mode poster generator + reward flag on the finder page.
- Community found-map, bulk/organisation tags, NFC write support.
- Native React Native wrapper that reuses the FastAPI backend.

## License

MIT — see [`LICENSE`](./LICENSE). 

## Team

**Founder — Anand Lakhera** — an.31and@gmail.com · +91 89042 23100  
LinkedIn: [linkedin.com/in/anand-lakhera](https://www.linkedin.com/in/anand-lakhera/) · Instagram: [@anandlakhera8](https://www.instagram.com/anandlakhera8)  
**Co-Founder — Devesh Sen**

Want to sponsor a batch of free physical stickers? Use the form on the
landing page or email directly. 🇮🇳
