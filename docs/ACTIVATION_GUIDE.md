# Info-Tag — Alert Channels Activation Guide

*How to switch on Email, WhatsApp, SMS and Masked Calling — step by step.*

**The most important thing to know: you do NOT need to change any code.**
Every channel is already fully implemented in the backend. Each one wakes up
automatically when it finds its environment variables. No env vars = the app
still works perfectly, it just skips that channel.

```
                 ┌────────────────────────────────────────────┐
 Finder scans →  │  Info-Tag backend (notifications.py)        │
 sends message   │                                            │
                 │  notify_owner() fans out to:               │
                 │   ├─ Email     → if SMTP/SendGrid vars set │
                 │   ├─ WhatsApp  → if Meta Cloud API vars set│
                 │   └─ SMS       → if Twilio vars set        │
                 └────────────────────────────────────────────┘
```

## 0. Quick reference — every switch in one table

| Channel | Environment variables | Cost | Where to get them |
|---|---|---|---|
| **Email (SMTP/Gmail)** | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM` | Free | Any mailbox provider (Gmail app password is easiest) |
| **Email (SendGrid)** | `SENDGRID_API_KEY`, `EMAIL_FROM` | Free tier: 100 mails/day | sendgrid.com |
| **Web Push** | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Free forever | `npx web-push generate-vapid-keys` |
| **WhatsApp** | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | Free (service conversations) | developers.facebook.com |
| **SMS** | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Paid (~₹0.5–7/SMS) | twilio.com |
| **Masked calls** | same three Twilio vars | Paid (per-minute voice) | twilio.com |

Where do the variables go?

- **Docker**: put them in `backend/.env` (loaded by `load_dotenv` on boot),
  then `docker compose up --build` again.
- **Without Docker**: same `backend/.env` file, then restart
  `uvicorn server:app --host 0.0.0.0 --port 8001`.
- **Cloud host (Render/Railway/Fly/EC2 etc.)**: add them in the host's
  "Environment Variables" screen and redeploy.

How to check what's on: open `https://<your-site>/api/features`. It returns
something like:

```json
{
  "email": true, "whatsapp": false, "sms": false,
  "twilio": false, "masked_calls": false,
  "callback_relay": true, "direct_deep_links": true
}
```

`callback_relay` and `direct_deep_links` are **always true** — those are the
free contact paths that never need a provider.

---

## 1. Email — start here (free, 10 minutes)

Email is the default alert channel: every finder message / callback request
emails the owner. Two options — pick ONE.

### Option A: Gmail SMTP (simplest, free)

1. Use (or create) a Gmail account for the app, e.g. `infotag.alerts@gmail.com`.
2. Turn on **2-Step Verification**: myaccount.google.com → Security.
3. Create an **App Password**: myaccount.google.com/apppasswords →
   name it "Info-Tag" → Google shows a 16-character password. Copy it.
4. Add to `backend/.env`:

   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=infotag.alerts@gmail.com
   SMTP_PASS=abcd efgh ijkl mnop   # the 16-char app password (spaces ok to remove)
   EMAIL_FROM=infotag.alerts@gmail.com
   ```

5. Restart the backend. `/api/features` should now show `"email": true`.

> Gmail limit: ~500 mails/day — plenty to start. Later, move to SendGrid or
> Amazon SES for higher volume.

### Option B: SendGrid (free 100/day, better deliverability)

1. Sign up at sendgrid.com → Settings → **API Keys** → Create API Key
   (Full Access → Mail Send is enough).
2. Verify a sender: Settings → **Sender Authentication** → verify your
   from-address (or your whole domain — better).
3. Add to `backend/.env`:

   ```env
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxx
   EMAIL_FROM=alerts@info-tag.in
   ```

4. Restart. Done — the code prefers SendGrid automatically when both are set.

### Test it

Scan any tag's finder page and send a message, or:

```bash
curl -X POST https://<your-site>/api/public/tags/<slug>/messages \
  -H "Content-Type: application/json" \
  -d '{"action_type":"message","body":"test alert","finder_name":"Tester"}'
```

The tag owner's inbox (and email) should receive it.

---

## 2. WhatsApp — Meta WhatsApp Cloud API (free tier)

This lets Info-Tag send owners a WhatsApp message every time their tag gets a
finder action. Meta's Cloud API is free for "service conversations"
(user-initiated / utility messages within limits), which fits Info-Tag's tiny
volume perfectly.

### Step-by-step

1. **Create a Meta developer account**: developers.facebook.com → Get Started.
2. **Create an app**: My Apps → Create App → type **Business** → name it
   "Info-Tag Alerts".
3. **Add the WhatsApp product**: on the app dashboard, find *WhatsApp* →
   **Set up**. Meta auto-creates a **test business phone number** for you.
4. On *WhatsApp → API Setup* you'll see the two values you need:
   - **Temporary access token** (24h, fine for testing)
   - **Phone number ID** (a long number under the "From" dropdown — this is
     NOT the phone number itself)
5. **Add recipients (test mode)**: in the "To" section, add up to 5 phone
   numbers (each gets a verification code on WhatsApp). While the app is in
   test mode, you can only message these numbers — enough to try it out.
6. Add to `backend/.env`:

   ```env
   WHATSAPP_TOKEN=EAAG...your-token...
   WHATSAPP_PHONE_NUMBER_ID=123456789012345
   ```

7. Restart. `/api/features` → `"whatsapp": true`.
8. In the Info-Tag app: **Settings → Phone & alerts** → enter your phone with
   country code (+91…) → switch ON **"WhatsApp me finder alerts"**.
9. Scan a tag, send a message — the owner gets a WhatsApp.

### Going live (beyond 5 test numbers)

1. **Permanent token**: Business Settings (business.facebook.com) → Users →
   **System Users** → create one (Admin) → Generate Token → select your app →
   check `whatsapp_business_messaging` — this token never expires. Put it in
   `WHATSAPP_TOKEN`.
2. **Real number**: WhatsApp → API Setup → Add phone number. Use a number
   that is NOT already on the WhatsApp app (a spare SIM or virtual number).
   Verify it by SMS/voice.
3. **Business verification**: Meta may ask for business verification for
   higher messaging limits — start it in Business Settings → Security Centre.
4. Free-form ("service") messages can only be sent within **24 hours of the
   user last messaging you**. For alerts outside that window, WhatsApp
   requires an approved **template message**. Easy fix that costs nothing:
   ask owners to send one "hi" to your WhatsApp number when enabling alerts
   (this also opts them in properly). Templates can be added later.

### Test the token directly (before touching Info-Tag)

```bash
curl -X POST "https://graph.facebook.com/v19.0/<PHONE_NUMBER_ID>/messages" \
  -H "Authorization: Bearer <WHATSAPP_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"messaging_product":"whatsapp","to":"91XXXXXXXXXX","type":"text","text":{"body":"Hello from Info-Tag!"}}'
```

If this works, Info-Tag's alerts will work.

---

## 3. SMS — Twilio (paid, optional)

Email + WhatsApp cover most users for free. Add SMS only if you want alerts
to reach owners with no internet.

1. **Sign up** at twilio.com — the trial gives free credit.
2. From the Console dashboard copy **Account SID** and **Auth Token**.
3. **Buy a number**: Console → Phone Numbers → Buy a Number → pick one with
   SMS capability (a US number ~$1/month works for testing; it can send to
   India at international rates).
4. Add to `backend/.env`:

   ```env
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_FROM_NUMBER=+1xxxxxxxxxx
   ```

5. Restart. `/api/features` → `"sms": true, "masked_calls": true`.
6. In the app: Settings → Phone & alerts → switch ON **"SMS me finder alerts"**.

> **India reality check (important):** sending commercial SMS *into India
> from Indian numbers* requires **DLT registration** (TRAI rule): you
> register your business, sender ID and message templates with an operator
> (Jio/Airtel/Vodafone DLT portals) and connect it to your SMS provider.
> Twilio international routes work without DLT but cost more (~₹5–7/SMS).
> Cheaper India-first alternatives when you're ready: **MSG91**,
> **Fast2SMS**, **Kaleyra** (~₹0.15–0.25/SMS after DLT). Since Info-Tag treats
> SMS as one gated function (`send_sms` in `backend/notifications.py`),
> swapping Twilio for MSG91 later is a ~20-line change in one file.
> Trial-account note: Twilio trials can only SMS/call numbers you verify in
> the Twilio console first.

---

## 3.5 Web Push — free phone notifications (no phone number needed!)

Web Push pops a notification on the owner's phone/laptop the moment a tag is
scanned or a finder writes — delivered by the browser vendors, so it is
**free forever**. It needs one thing: a VAPID key pair (a public + private
key that proves the pushes come from your server).

1. **Generate keys once** (either command works):

   ```bash
   npx web-push generate-vapid-keys
   # or, using the Python tool installed with the backend:
   vapid --gen        # prints private_key.pem/public_key.pem
   ```

   The `npx` route prints the two base64 strings directly — easiest.

2. Add to `backend/.env`:

   ```env
   VAPID_PUBLIC_KEY=BPz...your-public-key...
   VAPID_PRIVATE_KEY=x3T...your-private-key...
   VAPID_SUBJECT=mailto:an.31and@gmail.com
   ```

3. Restart. `/api/features` → `"web_push": true`.
4. Each owner then goes to **Settings → Phone notifications (free)** →
   **Turn on notifications** → the browser asks permission → a test
   notification arrives immediately.
5. What triggers a push after that:
   - a finder message / quick action / callback request → always
   - a scan → only if the owner enabled "notify me on every scan"

Notes:
- Requires HTTPS (or localhost) — push does not work on plain http.
- On iPhone, the owner must first **Add to Home Screen** (install the PWA);
  iOS only allows push for installed web apps (iOS 16.4+).
- Dead subscriptions (uninstalled browsers) are pruned automatically.

## 4. Masked calling — the same Twilio account

Masked calling = a finder taps "call", Twilio rings *them*, then connects
them to the owner. **Neither person ever sees the other's number** — both
only see your Twilio number.

- It switches on automatically with the same three Twilio variables — no
  extra setup, no code change. (`start_masked_call` in
  `backend/notifications.py` does the bridging with inline TwiML.)
- Voice calls to India cost per minute; check Twilio's voice pricing.
- **The free alternative is always on**: the "Request a call back" form on
  every masked tag. The finder leaves *their* number, the owner gets alerted
  on every channel and calls back. The owner's number stays hidden — ₹0.

---

## 5. What the owner does in the app (after you activate channels)

1. **Settings → Phone & alerts**: enter phone number with country code
   (+91…), toggle WhatsApp / SMS alerts.
2. **Per tag → "How can finders reach you?"**:
   - **Masked (recommended)** — number hidden, callback relay (+ masked
     calling if Twilio is on).
   - **Direct** — finder page shows Call / WhatsApp / SMS buttons with your
     number; toggle each button on/off. Free — these are plain phone links,
     they never need a provider.
3. Optional: add a **Reward for the finder** on any tag — it shows as a gold
   banner on the finder page.

## 6. Complete `.env` example

```env
# --- core (required) ---
JWT_SECRET=change-me-to-a-long-random-string
ADMIN_EMAIL=anand@info-tag.in
ADMIN_PASSWORD=change-me
SITE_URL=https://info-tag.in
MONGO_URL=mongodb://mongo:27017
DB_NAME=infotag

# --- email (pick ONE option) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=infotag.alerts@gmail.com
SMTP_PASS=xxxxxxxxxxxxxxxx
EMAIL_FROM=infotag.alerts@gmail.com
# SENDGRID_API_KEY=SG.xxxxxxxx        # alternative to SMTP

# --- whatsapp (free tier) ---
WHATSAPP_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=123456789012345

# --- sms + masked calls (paid, optional) ---
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
```

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| `/api/features` shows a channel `false` after setting vars | Restart the backend — env vars load at boot. Check for typos in variable names. |
| Email lands in spam | Use SendGrid/SES with domain verification (SPF/DKIM), or keep Gmail for testing. |
| WhatsApp works for you, not for others | App is in test mode — add their numbers as recipients, or complete the going-live steps. |
| WhatsApp "message not delivered" after some hours | 24-hour service window — ask owners to message your WhatsApp number once, or add a template. |
| Twilio error 21608 | Trial account: verify the destination number in the Twilio console. |
| SMS to India fails/expensive | DLT rules — see the India note in section 3; consider MSG91/Fast2SMS. |
| Nothing at all is sent | Backend logs say why: every skipped channel logs a line like "WhatsApp skipped (not configured)". |

## 8. Where this lives in the code (for the curious)

| What | File |
|---|---|
| All providers + `notify_owner()` fan-out | `backend/notifications.py` |
| Callback request + masked-call endpoints | `backend/routes/contact_routes.py` |
| Finder page contact buttons (masked/direct) | `backend/routes/finder_ssr.py` |
| Per-tag contact block + public contact API | `backend/routes/tag_routes.py`, `backend/models.py` |
| Owner phone & alert toggles | `backend/routes/auth_routes.py`, `frontend/src/components/settings/SettingsParts.jsx` |
| Feature flags endpoint | `backend/server.py` → `GET /api/features` |
