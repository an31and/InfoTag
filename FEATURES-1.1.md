# Info-Tag — Release 1.1 feature set

This branch (`features-1.1`) collects everything built after the initial
go-live. `main` is left untouched for today's production launch; this branch is
where 1.1 is staged for review and a later merge.

Two of the items below (the WhatsApp Cloud API webhook and the first batch of
Indian-language translations + the video reel) already shipped to `main` via
PR #5 and are described here for completeness. Everything else is new in 1.1
and sits in the four commits on top of `main`.

---

## 1. Phone-number signup (email optional)

Owners can now create an account with **just a mobile number** — email is
optional. This is the headline change for reaching users who have a phone but
no email address.

- **Signup:** mobile number is the primary field (with a `+91…` country-code
  hint); email is clearly marked *(optional)*. At least one of the two is
  required; password is always required.
- **Login:** a single "mobile number or email" field — people sign in with
  whichever they used.
- **Format-proof matching:** `+91 98765 43210`, `9876543210`, and
  `091-98765-43210` all resolve to the same account. Internally we store a
  canonical `phone_digits` key (the last 10 digits) used for both login lookup
  and the "one number = one account" uniqueness rule.
- **No new infrastructure:** login stays password-based, so this needs no SMS
  or WhatsApp provider. (OTP verification can be layered on later — see §6.)
- **Safe data model:** email uniqueness is now enforced only when an email is
  present (partial index); a new partial-unique index guards `phone_digits`.
  Both index migrations are best-effort so they can't crash startup on
  existing data. The login session already keys off the user id, so phone-only
  accounts get valid sessions with no token changes.

Files: `backend/models.py`, `backend/routes/auth_routes.py`, `backend/db.py`,
`frontend/src/pages/Auth.jsx`, `frontend/src/components/auth/AuthParts.jsx`,
`frontend/src/lib/auth.jsx`, i18n in all 7 languages.
Tests: `backend/tests/test_phone_auth.py` (11 cases).

---

## 2. Admin control — turn landing sections on/off

A **"Landing page sections"** panel in the admin portal with a switch per
section: video reel, live counters, how-it-works, use-cases, features,
get-tags, sponsor, FAQs, WhatsApp band, and feedback.

- Toggling a switch saves server-side and applies to **every visitor
  instantly — no code change or redeploy.**
- Every section defaults to ON, so a missing setting or a newly added section
  never blanks the page.
- Backed by a `settings` collection (`id="site"`), an admin-gated
  `GET/PATCH /api/admin/settings`, and a public
  `GET /api/public/site-settings` the landing page reads on load.

Files: `backend/routes/admin_routes.py`, `backend/routes/public_routes.py`,
`frontend/src/pages/Admin.jsx`, `frontend/src/pages/Landing.jsx`.
Tests: `backend/tests/test_admin_settings.py` (4 cases).

---

## 3. Mobile page-length optimization

The landing page was very long on phones — 8 use-case cards + 9 feature cards
+ 4 product cards stacked vertically (21 full-width cards).

- On mobile, each of those three grids is now a **single horizontal
  swipe row** (the same snap-scroll gesture as the video reel), with the next
  card peeking in so it's obvious you can swipe.
- On tablet/desktop they stay as the full grids.
- Combined with the admin toggles (§2), the page can be made as short as you
  like without touching code.

Files: `frontend/src/pages/Landing.jsx`.

---

## 4. WhatsApp diagnostics in the admin portal

The send path (`send_whatsapp`) is fire-and-forget and swallows Meta's error,
so a misconfigured setup fails **silently**. This makes the failure visible.

- **"WhatsApp diagnostics"** panel in the admin portal:
  - a config checklist (which env vars are set — booleans only, never the
    secret values),
  - a **live token check** (a `GET` against the Graph API that validates the
    token + phone-number-id pair without sending anything),
  - a **"send test to my number"** box that prints **Meta's exact response**,
    so the cause is obvious (e.g. `131047` = 24-hour window not open,
    `190` = expired token, `131030` = number not in the test-mode allowlist).
- Endpoints: `GET /api/admin/whatsapp/health`, `POST /api/admin/whatsapp/test`
  (both admin-gated).

Files: `backend/notifications.py`, `backend/routes/admin_routes.py`,
`frontend/src/pages/Admin.jsx`.
Tests: `backend/tests/test_whatsapp_diag.py` (5 cases).

---

## 5. Video reel improvements & returning-visitor cache fix

- **Sound control:** each 10-second clip gets a speaker button. Autoplay must
  start muted (browser policy); one tap turns sound on, and only one clip can
  be unmuted at a time (swiping away re-mutes).
- **Easy to add videos:** the reel is config-driven via
  `frontend/src/constants/videos.js` — drop an MP4 in `public/videos/` and add
  one line, or use `{ youtubeId }` for a click-to-load YouTube embed
  (thumbnail only until tapped, so the page stays light).
- **Cache fix:** `index.html` now sends `Cache-Control: no-cache`. It
  previously had no cache rule, so a returning browser (e.g. a laptop that had
  visited before a deploy) kept a stale `index.html` pointing at deleted JS
  bundles — the site worked for new visitors but broke for returning ones.
  A 7-day cache policy was also added for `/videos/`.

Files: `frontend/src/components/UseCaseVideos.jsx`,
`frontend/src/constants/videos.js`, `frontend/nginx.conf`.

---

## 6. Already live via PR #5 (recap)

Shipped to `main` before this branch; included here for a complete 1.1 picture.

- **7 Indian languages:** full dictionaries for Hindi, English, Marathi,
  Bengali, Tamil, Telugu, Kannada (previously only Hindi/English were complete;
  the rest fell back to English). Split into per-language files; the 5 regional
  locales are code-split into ~12 KB lazy chunks. **Default language is Hindi**,
  with a one-time first-visit language picker.
- **Server-rendered finder page** carries all 7 languages with a zero-JS
  `?lang=` switcher and Accept-Language matching (default Hindi).
- **Use-case video reel** under the hero (mobile-first swipeable).
- **WhatsApp Cloud API webhook** — GET verification handshake + POST event
  receiver that logs delivery status and opens Meta's free 24-hour customer
  service window when an owner messages the business number. Env-gated;
  `X-Hub-Signature-256` verification when `META_APP_SECRET` is set.
- **Settings opt-in** — a one-tap "message us to activate" link so WhatsApp
  alerts stay inside Meta's free window.
- Compact mobile nav.

---

## Deferred (not in this branch)

- **OTP verification for signup** (SMS or WhatsApp). Phone signup here is
  password-based and unverified, consistent with email today. WhatsApp OTP for
  brand-new users additionally needs a Meta-approved *authentication template*
  (a new user is outside the 24-hour window). Twilio SMS is intentionally
  avoided — it's paid.

---

## Verification summary

- Backend: **29 tests pass** (`test_phone_auth`, `test_admin_settings`,
  `test_whatsapp_diag`, `test_webhook_whatsapp`) — run in-process with
  `mongomock-motor`, no external services.
- Frontend: production build compiles clean.
- UI flows (signup/login payloads, section toggles, swipe rows, translated
  sections, video sound) were driven and screenshotted with Playwright at
  mobile (390 px) and desktop (1440 px) viewports.

> Note: the regional-language strings are carefully written but
> machine-translated — a quick native-speaker pass on Tamil/Telugu/Kannada is
> recommended before a large marketing push.
