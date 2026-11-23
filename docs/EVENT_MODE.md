# Event Mode — bulk QR tags, organiser logins, Digital IDs

Generate QR tags in bulk for any event with no code changes, give each event
organiser a login that sees **only their own tags**, and hand guests a printed
sticker, a badge, a guest pack, or a **Digital ID** on their phone.
Tags are **permanent**: they keep working after the event.

---

## 1. Quick start (admin)

1. **Admin → Organisations & organiser logins** → *Add organisation*
   (e.g. "Prathivi Parikrma Samiti").
2. Open the organisation → *Organiser logins* → enter the organiser's email →
   *Create login*. Copy the credentials or tap **Share on WhatsApp**. The
   password is shown only once; use *Reset password* if it is lost.
3. **Events → New event** → choose the organisation, name, code (e.g. `PK24`),
   number of tags, and what you will print → *Create event & generate tags*.
4. On the event page → **Print** → pick the sheet preset (or *Custom* to match
   your purchased label sheet), print the **calibration page** first, then
   download the PDFs (max 250 tags each). Also print the **event poster**.
5. Optional: **Digital IDs** → download every tag's Digital ID link (CSV) and
   send links on WhatsApp instead of (or as well as) stickers.

Organisers sign in at the normal `/login` page and land on **Events**.

## 2. Who can do what

| Action | Admin | Organiser | Organiser with "may generate tags" |
|---|---|---|---|
| See / print / export their org's events | ✅ all orgs | ✅ own org only | ✅ own org only |
| Help desk: look up code, message owner, mark returned | ✅ | ✅ | ✅ |
| Edit event texts, close registrations, archive | ✅ | ✅ | ✅ |
| Create events, add 10% spare tags | ✅ | ❌ | ✅ (up to the org's max tags/event) |
| Revoke / restore a batch | ✅ | ❌ | ❌ |
| Create organisations and logins | ✅ | ❌ | ❌ |

Enforced on the server (`backend/routes/event_routes.py`): anything outside an
organiser's organisation returns **404**. Disabling an organisation blocks its
organisers immediately.

## 3. What a guest sees

* **Scan an unregistered sticker** → one screen (Hindi/English, works without
  JavaScript): name, mobile and/or email, a one-tap choice of item (phone, bag,
  bottle, other), *keep my number private* (default) or *show my number*, a
  WhatsApp opt-in tick, and consent. Then *Register*. This takes about 30 seconds.
* **Guest packs** (name card + 3 stickers): registering any one sticker links
  all 4 to the same owner, and the guest gets **one** confirmation.
* After registering, the guest gets:
  * **Turn on WhatsApp alerts**. This opens WhatsApp with `START PK24-0001-XXXX`.
    Sending it opens Meta's free 24-hour window, so alerts cost ₹0. Guests
    never receive paid template messages.
  * **Email** confirmation, if they gave an email.
  * A **Digital ID** link, which is private and also lets them mark the item returned.
* **Someone who finds the item** scans the sticker (or types the short code at
  `/c` or on the event page) and gets the usual finder page: masked callback,
  message, "I found this". The owner's number never appears unless they chose
  *show my number*.
* Medical / emergency mode is **never** available on event tags.

### Digital ID

`/id/<token>`: a card with the QR, short code, event name and (with the
owner's private link) their name and item. Buttons:

* **Save card image**: a PNG made in the browser, so it costs the server nothing.
* **Save as phone wallpaper**: a 1080×2340 lock screen. If the phone is lost,
  whoever finds it can scan the lock screen.
* **Share** (Web Share / WhatsApp), **Print**.

## 4. Printing

* Presets: **12 / 24 / 35 per A4**, **ID badges** (54×85.6 mm, lanyard slot
  mark, hand-write name line), **guest packs** (8 guests per A4).
* **Custom**: page size, margins, rows × columns, label size, gaps and QR size,
  all in mm, to match any purchased sheet.
* **Start from label #N** reuses part-used sheets. **Shift right/down**
  corrects printer offset (find it with the calibration page). Cut marks are optional.
* Each QR cell has the QR (vector, black on white, minimum 20 mm, 4-module quiet
  zone), the short code, and **"मिला? स्कैन करें / Found? Scan"**. No phone
  numbers or personal data are printed on tags.
* Use a **laser** printer: toner survives water, inkjet smudges. Paper labels
  peel off bottles; use vinyl labels or clear tape for drinkware.
* Max **250 tags per PDF**. Bigger events get several files (*Download all*
  fetches them one by one). Files are regenerated on demand, so any chunk can
  be reprinted at any time and nothing is stored.

## 5. How it scales (signed tokens)

Each printed QR holds `HTTPS://<HOST>/T/<28-char token>`, where:

```
token = base32( version | batch_id(3B) | serial(3B) | HMAC-SHA256(key, …)[:10B] )   # 80-bit signature
code  = PK24-0137-7QX2   (event code, serial, 20-bit HMAC check)
```

* **Unregistered tags have no database row.** The server checks the signature.
  A row is written only when a tag is registered (`tags` collection, so every
  existing feature such as inbox, alerts and masked callback works unchanged).
* Upper-case URLs use the compact QR alphanumeric mode (version 4 at error
  correction H), which scans better on small stickers.
* Dashboards read counters (`events.stats`, `stats_daily`), never
  `count_documents` over millions of rows. Lists are keyset- or serial-paged.
* Measured: **1,000,000 token verifications in ~9.6 s on one CPU core**
  (`python scripts/bench_tokens.py`). A 250-tag PDF renders in ~1.6 s locally.

Rough MongoDB storage (Atlas M0 = 512 MB), assuming 40% of tags get registered:

| Tags | One row per tag (old design) | Signed tokens (this design) |
|---|---|---|
| 200 | ~0.2 MB | ~0.05 MB |
| 100,000 | ~100 MB | ~25 MB |
| 1,000,000 | ~1 GB (doesn't fit M0) | ~250 MB, 0 MB for unregistered tags |

**Existing tags keep working:** `/api/finder/<slug>` is unchanged, and
`/t/<slug>` and `/c/<slug>` redirect old slugs too.

## 6. ⚠️ Signing keys: tags depend on them forever

* Set `TAG_SIGNING_KEYS=k1:<≥32-char secret>` in production and **store it in
  a password manager**. If it isn't set, a key is created once and kept in
  MongoDB (`settings` collection). Back up the database.
* Never remove a key. To change keys, **add** `k2:…`. New batches use the
  newest key, and old printed tags keep verifying with theirs.
* Losing every key means every **unregistered** printed tag stops working.
  Registered tags still work by their short code.
* `TAG_QR_BASE` (optional) sets the host printed in QRs. Keep it short and
  stable, because printed tags last forever.

## 7. Abuse and privacy safeguards

* **Shared-WiFi friendly limits.** Limits apply per anonymous browser cookie
  (strict), per event (generous) and per IP (loose flood ceiling only), so 200
  guests on one venue IP can all register. This is tested.
* Honeypot fields on every public form. Hashed IPs only.
* Organisers see an owner's name plus `•••• 1234` / `a•••@mail` hints. They
  contact owners through **Message owner**, which relays the message without
  revealing numbers.
* The report CSV excludes names unless *Include owner names* is ticked.
* Revoke a whole batch or a serial range (admin) if stickers are stolen.
  Revoking can be undone.

## 8. Event-day checklist and fallback plan

**Day before**
* UptimeRobot (free) pings `/api/health` every 5 minutes, so the Render free
  instance never sleeps. Open the site 30 minutes before gates open.
* Print the calibration page, then one test sheet, and scan 5 random stickers
  with Android and iPhone cameras.
* Print the **event poster** (shared QR) for the help desk and entrances.
* Test the full flow on a real phone over mobile data: scan, register, WhatsApp
  `START`, finder "I found this", owner alert.

**At the venue: lost & found desk (works even if the internet is down)**
1. A volunteer and a paper register with columns: code on the sticker · item ·
   where found · time · finder's name.
2. Items with a sticker: Events → Tags → **Look up a code**, then
   **Message owner** ("Your bag is at Gate 2"), then **Mark returned** when collected.
3. No internet: write the code in the register and announce it on the PA
   ("tag ending 7QX2"). Update the app later.
4. Items without a sticker: paper register plus the PA system, as usual.
5. After the event, shred any printed lists with names.

## 9. API summary

Admin / organiser (`/api/events`, cookie auth):
`GET /meta`, `GET|POST /`, `GET|PATCH /{id}`, `POST /{id}/batches`,
`POST /{id}/batches/{bid}/revoke|restore` (admin), `GET /{id}/tags`,
`GET /{id}/lookup?code=`, `POST /{id}/tags/{serial}/returned|notify`,
`GET /{id}/print/manifest`, `GET /{id}/print.pdf`, `GET /{id}/poster.pdf`,
`GET /print/calibration.pdf`, `GET /print/presets`, `GET /{id}/report.csv`,
`GET /{id}/digital-ids.csv`, `GET /{id}/daily`.

Admin (`/api/admin/orgs`): list/create/update organisations; create, reset
and remove organiser logins.

Public (server-rendered): `GET /t/{token}`, `POST /t/{token}/claim`,
`GET /c/{code}`, `GET /e/{code}`, `GET /id/{token}`,
`POST /id/{token}/returned`. WhatsApp webhook understands `START <code>`.

## 10. Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest            # 34 offline tests, in-memory MongoDB
python scripts/bench_tokens.py   # 1M-verification load test
```

## 11. Not built yet (next phases)

* Public General Lost/Found board; the poster page `/e/<code>` becomes its
  event-filtered view.
* CSV guest import (names on guest-pack cards; phone only with consent).
* Cloudflare Pages Function "cold-start shield" for `/t/*`.
* Personal-data purge per event (tags stay; owner contact data is deleted).

## 12. Recovery tracking on event tags

Event tags take part in owner-confirmed recovery tracking. See
`docs/RECOVERY_TRACKING.md` → *Event Mode tags*. In short:

* Organiser **Mark returned** never counts as a confirmed recovery.
* The guest's own Digital ID **"I got my item back"** does count, but only
  after a finder contacted them.
