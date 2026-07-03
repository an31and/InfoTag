# Info-Tag — Competitive Analysis & Feature Roadmap

*Prepared 2026-07-03 · Owner: Anand Lakhera · Co-Founder: Devesh Sen*

Info-Tag's positioning: **free (or as close to ₹0 as possible), privacy-first,
no-app smart tags**. This document compares the Indian QR-tag market and maps
which competitor features we adopt, improve, or deliberately skip — always
choosing the zero-cost path first.

## 1. Competitor snapshot

| Product | Contact model | Pricing | Notes |
|---|---|---|---|
| **GetBackLost** (getbacklost.in) | Sells *separate physical products* for "Mask calling" vs "Direct Calling" (keychains, luggage tags, pet pendants) | ~₹99+ per tag (coupon deals), free shipping | Email scan alerts, scan location, battery-free, no app, lifetime validity |
| **LostTag / EkTag** (ektag.app) | Anonymous reach-the-owner relay | Paid physical tags | "Tag anything" — vehicles, keys, luggage, pets; Made in India; no app for finders |
| **Car Sampark Tag / NGF132** (sampark.me) | Masked calls + SMS + WhatsApp notifications, virtual number | ₹2,999 / 20 tags | Focused on vehicle/parking use case |
| **LetzScan** (letzscan.com) | Vehicle parking QR | ₹132 / tag, ₹399 / 2 | Parking-first positioning |
| **LostIt Tag** (lostittag.com) | In-app secure chat, reward incentives, community lost-map | $20/year subscription | App-required — the model Info-Tag explicitly rejects |

### What every paid competitor charges for — and how Info-Tag does it free

| Competitor feature | Their cost | Info-Tag's approach |
|---|---|---|
| Direct-calling tag | Separate ₹99+ product | **Per-tag toggle** — `direct` mode renders free `tel:` / `wa.me` / `sms:` deep links. ₹0, no telephony provider. |
| Mask-calling tag | Separate ₹99+ product / virtual number plans | **Default `masked` mode** — reverse relay: the finder leaves *their* number, the owner calls back. Owner's number is never disclosed. ₹0. Optional Twilio bridge (env-gated) hides *both* numbers for deployments that want it. |
| WhatsApp scan alerts | Subscription tier | Meta WhatsApp Cloud API — free service-conversation tier, env-gated, off by default. |
| SMS alerts | Subscription tier | Twilio SMS, env-gated (the only genuinely paid channel; email + WhatsApp cover most users free). |
| Physical tags | ₹99–₹2,999 | Self-printed A4/ID-card/keyring PDFs (already shipped) + community **Sponsor-a-tag** for printed batches. |
| Scan alerts + location | Included in tag price | Already free: email alert, hashed-IP scan log, opt-in finder geolocation. |

## 2. The mask / no-mask contact model (shipped in this iteration)

Competitors force the choice at **purchase time** (you buy a "mask" tag or a
"direct" tag). Info-Tag makes it a **per-tag software toggle** — the same
printed QR can switch modes anytime:

- **Masked (default, privacy-first)** — the finder page never contains the
  owner's number. Finder options: anonymous message, quick actions, and
  **Request a call back** (finder leaves their number; owner is alerted on
  email/WhatsApp/SMS and calls back). Optional **masked-call bridge**
  (Twilio, env-gated): Twilio rings the finder, dials the owner with the
  Twilio number as caller ID — neither side sees the other's number.
- **Direct (zero-friction)** — the finder page shows one-tap
  **Call / WhatsApp / SMS** buttons using the owner's number, each channel
  individually toggleable. Free forever because it's just deep links.

Owner alert fan-out on every finder action: **email** (free) +
**WhatsApp** (free tier, env-gated) + **SMS** (env-gated), controlled per
user in Settings → Phone & alerts.

## 3. Shipped in this iteration

1. Per-tag contact mode (masked/direct) with per-channel toggles — backend
   model, owner UI, SSR finder page (EN + HI), SPA finder view API.
2. Owner phone + WhatsApp/SMS alert preferences (Settings → Phone & alerts).
3. Real WhatsApp Cloud API + Twilio SMS + Twilio masked-call bridge
   integrations (all env-gated; zero-config deployments still work).
4. Free callback-request relay (`POST /api/public/tags/{slug}/call-request`).
5. Animated landing page: interactive "Info-Tag in action" use-case scenes
   (wrong parking, masked call, lost & found, medical ID) built with pure
   CSS keyframes, honoring `prefers-reduced-motion`.
6. Co-founder credit: Devesh Sen (+91 89042 23100 shown as org contact).

## 4. Roadmap — ranked by impact ÷ cost

### P1 (next)
- **Phone verification (OTP via free email fallback / WhatsApp)** before a
  tag may switch to direct mode — prevents pointing a tag at someone else's
  number.
- **Scan-alert push notifications** via the existing PWA service worker
  (Web Push is free; competitors charge for scan alerts).
- **Reward note on finder page** — LostIt-style "reward offered" flag on a
  lost tag; costs nothing, measurably improves return rates.
- **Lost-mode poster generator** — one-click A4 "LOST" poster PDF with the
  tag QR (reuses the existing PDF pipeline).

### P2
- **Community found-map** (privacy-safe: city-level pins of recovered items)
  for the landing page social proof.
- **Bulk/organisation tags** — schools, delivery fleets, housing societies
  (Sampark sells 20-packs; we can serve this free with a CSV import + batch
  PDF).
- **NFC write support** — same slug URL written to cheap NTAG stickers;
  purely client-side (Web NFC), ₹0 server cost.
- **Vehicle-specific quick actions** — "blocking traffic", "accident alert"
  with optional photo upload.

### P3
- **Telegram alerts** (free Bot API — cheaper than SMS everywhere).
- **Self-serve sponsor marketplace** — sponsors fund printed batches for
  schools/NGOs, with public counters.
- **Native wrapper** (React Native) once PWA limits are actually hit.

### Deliberately not doing
- App-required finder flows (kills the core promise).
- Subscriptions for privacy features — masking stays free.
- Raw IP / location tracking of finders beyond opt-in geolocation.
