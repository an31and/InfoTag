# Info-Tag — Product Requirements Document

## Original problem statement
Info-Tag is a privacy-first, no-app (for finders), mobile-first, lightweight,
Made-in-India, free public-service smart-tag ecosystem.  Mission: help ordinary
people recover lost items (vehicles, pets, luggage, keys) and let first
responders read critical medical info in seconds — free of cost.

Founder & owner: Anand Lakhera — +91 89042 23100 · an.31and@gmail.com
Co-Founder: Devesh Sen

## Architecture
- **Backend** — FastAPI + Motor (async MongoDB) on port 8001.  All routes under
  `/api`.  JWT cookie auth (httpOnly, secure, samesite=none).  Cookies issued by
  the same helper for both password and Emergent Google login.
- **Frontend** — React + Tailwind, CRA build, configured as a PWA (manifest +
  service worker for the shell, `display: standalone`, installable).
- **MongoDB** — collections: `users`, `tags`, `profiles`, `scans`, `messages`,
  `login_attempts`.  Indexes on email (unique), slug (unique), owner_id,
  tag_id.

## User personas
- **Owner** (PWA user) — signs up, creates tags, prints stickers, monitors
  scans + finder inbox, optionally fills a medical emergency profile.
- **Finder** — anyone with a phone camera.  Never installs an app.  Sees the
  finder page and can send a message back to the owner anonymously.
- **First responder** — sees the medical emergency view instantly when the
  owner has enabled it with consent.

## Core requirements (static)
1. **Privacy first** — owner's phone is never exposed; finders reach the
   owner only via server-side relays.  Slugs are 7-char unguessable.
2. **No app for finders** — `/tag/:slug` is a pure web page.  Lightweight,
   no shadcn, system-font fallback, mobile-first.
3. **PWA for owners** — installable on Android/iOS via web manifest.
4. **Medical Emergency Mode** — strict consent + accuracy notice; reserved
   red color; tel: button.
5. **i18n** — English default, Hindi + Marathi + Bengali + Tamil ship in
   the dictionary, more drop in trivially.
6. **Both auth options** — JWT email/password + Emergent Google login.
7. **Free public service** — no paywall; advanced tier (WhatsApp/Twilio)
   wired as documented placeholders behind feature flags.

## What's been implemented (2026-02-14)
- Backend: full CRUD, claim flow, public finder lookup with scan capture
  (de-duped per 30s + hashed-IP window), finder message endpoint
  (rate-limited + honeypot + HTML stripping), medical profile endpoints,
  PDF generator (A4/ID-card/keyring), WhatsApp/Twilio placeholder
  endpoints, email helper (env-gated), right-to-be-forgotten delete with
  password confirmation, account data export, JWT + Emergent Google
  session exchange (async via httpx), Sponsor-a-tag endpoint + public
  stats, admin + 3 demo tags seeded on boot. FastAPI lifespan context
  manager (no deprecation warnings).
- Frontend: Landing (with Sponsor section), Login/Signup, AuthCallback,
  Dashboard (with skeleton stat tiles), TagEdit, TagQR, TagMedical, Inbox,
  Settings, Finder, EmergencyView, Claim, Privacy/Terms/MedicalDisclaimer.
  PWA manifest + service worker. Light/dark theme. 5-language switcher
  (EN, HI, MR, BN, TA).
- DevX: docker-compose + per-folder Dockerfiles + nginx.conf + .env.example
  files for both backend & frontend, MIT LICENSE, CONTRIBUTING.md,
  root + per-folder READMEs, standalone seed.py.
- Testing: 33/33 backend pytest pass on iteration_1; iteration_2 verified
  the full backlog with new feature tests.

## What's been implemented (2026-07-03)
- **Mask / no-mask contact model** — per-tag `contact` block
  (`mode: masked|direct` + per-channel toggles).  Masked (default): finder
  page never contains the owner's number; callback-request relay
  (`POST /api/public/tags/{slug}/call-request`, free) + optional Twilio
  masked-call bridge (`POST /api/public/tags/{slug}/masked-call`,
  env-gated).  Direct: SSR finder page renders free tel:/wa.me/sms: deep
  links honoring per-channel toggles.
- **Multi-channel owner alerts** — `notify_owner()` fan-out: email +
  WhatsApp (Meta Cloud API: `WHATSAPP_TOKEN`+`WHATSAPP_PHONE_NUMBER_ID`) +
  SMS (Twilio: SID/token/`TWILIO_FROM_NUMBER`).  User model gains `phone`,
  `whatsapp_alerts`, `sms_alerts`; Settings → "Phone & alerts" UI.
- **Animated landing page** — interactive UseCaseShowcase (wrong parking /
  masked call / lost & found / medical ID scenes) with pure-CSS keyframes
  (scan-sweep, phone-ring, travel-dot, heartbeat…), all disabled under
  prefers-reduced-motion.  Hero tag list staggers in.
- **Docs** — `docs/PRODUCT_ANALYSIS.md`: competitor analysis (GetBackLost,
  EkTag, Sampark/NGF132, LetzScan, LostIt) + ranked free-first roadmap.

## Backlog / Next actions
- **P1** Skeletons on dashboard stat tiles instead of the em-dash placeholder.
- **P1** Migrate `requests.get` in `/api/auth/google/session` to `httpx.AsyncClient`
  so the event loop isn't blocked.
- **P1** Dedupe scan inserts within ~30s per (tag_id, ip_hash) so refresh-spam
  doesn't pollute scan counts.
- **P2** Migrate `@app.on_event` to FastAPI lifespan context manager.
- **P2** Server-side require `current_password` for `DELETE /api/auth/me`.
- **P2** Docker compose file at repo root + per-folder READMEs + MIT LICENSE
  for full GitHub-readiness (currently runnable inside the platform pod).
- **P2** Public-finder page SSR / 75 KB budget (currently client-rendered;
  works on 3G but can be slimmer).
- **P3** Real WhatsApp + Twilio integrations behind a `tier=paid` flag.
- **P3** Native React Native wrapper that reuses the FastAPI backend.

## Files of note
- `/app/backend/server.py`, `/app/backend/auth.py`, `/app/backend/db.py`
- `/app/backend/routes/*.py`
- `/app/frontend/src/App.js`, `/app/frontend/src/lib/{auth,i18n,theme}.jsx`
- `/app/frontend/src/pages/*.jsx`
- `/app/frontend/public/{manifest.json,sw.js,index.html}`
- `/app/memory/test_credentials.md`
- `/app/auth_testing.md`
