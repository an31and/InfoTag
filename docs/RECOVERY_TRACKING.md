# Recovery Tracking

The owner and finder talk outside our servers (calls, WhatsApp deep links,
callbacks), so we can't see an item being handed back. Recovery tracking gets
an honest "item found" number from inside the system: **only the owner's own
"yes" counts as a recovery.**

## Data model

Recovery data lives in its own collections. The `tags` collection is not
changed, so existing tags need **no migration**: a tag with no case simply has
no recovery history.

| Collection | Purpose |
|---|---|
| `recoveries` | One document per incident (case) |
| `recovery_events` | Append-only log: `scanned`, `finder_contacted`, `urgent_alert_sent`, `owner_prompted`, `reminder_sent`, `owner_response`, `marked_probable` |
| `recovery_tokens` | One-time owner links. Only the **SHA-256** of each token is stored. A Mongo TTL index (`purge_at`) cleans up old rows. |

Fields on a case (`recoveries`): `status`, `first_scan_at`, `first_contact_at`,
`owner_prompted_at`, `reminder_count`, `last_reminder_at`, `resolved_at`,
`resolution_source` (`owner_link` | `owner_dashboard`). There are also these
bookkeeping fields: `priority`, `scan_count`, `contact_count`,
`next_action_at`, `owner_response` and `urgent_alert_at`.

**Privacy:** cases and events hold no finder data at all: no IP (raw or
hashed), name, phone, message or location. Scan de-duplication still uses the
existing hashed-IP `scans` collection.

## Status lifecycle

```
scanned ─finder acts─▶ finder_contacted ─prompt sent─▶ awaiting_owner
                                                          │  "not yet" → stays, reminder re-armed
          owner_confirmed_found ◀── "yes" ────────────────┤
          (resolved_at set)        owner_not_found ◀─ "no"┤
                                                          ▼
                  reminder (2.5 d) → final reminder (2.5 d) → probable_unconfirmed (2.5 d)
```

* `scanned` is set on every recorded scan, after the existing 30 s hashed-IP
  dedupe. Scans attach to the open case. A scan-only case that has been idle
  for 14 days starts a new incident.
* `finder_contacted` is set on **every** finder action: message,
  wrong_parking, headlight_on, found, call-back request and masked call. This
  covers the JSON API and the SSR finder page.
* Only `"found"` sets `owner_confirmed_found` and `resolved_at`. `"not_found"`
  closes the case with no `resolved_at`.
* A late "yes" still counts. `probable_unconfirmed` and `owner_not_found`
  cases can still be answered from the dashboard.
* A new finder contact after a case is closed opens a new case.

## Owner confirmation

* The message goes through `notify_owner()` and is bilingual (Hindi and
  English). It links to `/recovery/confirm#t=<token>`. The token sits in the
  URL **fragment**, so it never reaches server logs or `Referer` headers.
* Opening the page is read-only (`GET /api/public/recovery/{token}`), so email
  scanners and chat link previews can't answer for the owner. Pressing a
  button sends `POST /api/public/recovery/{token}`, which consumes the token
  atomically.
* Each token is single-use and expires after 7 days. A final answer
  (yes or no) also voids every other open link for that case. Reuse returns
  409, an expired link returns 410, and an unknown token returns 404.
* The dashboard shows the same three buttons:
  `GET /api/recoveries/pending` and `POST /api/recoveries/{id}/respond`.

## Child, pet and medical tags (`special`, `pet`, `medical`)

* On the first finder contact, the owner gets an immediate 🚨 URGENT alert
  (`notify_owner(..., urgent=True)`). It goes by email, WhatsApp and SMS if
  they have a phone, even if WhatsApp/SMS alerts are switched off. It also
  goes by web push.
* The prompt "Have they been found safe?" follows 2 hours later and is sent
  by the sweeper.
* The Medical Emergency consent gate is unchanged. An emergency-mode medical
  page still shows data only when `emergency_mode && consent_given`. That
  page has no message form, so the only recovery event it records is the
  scan.

## Background job and cold starts (free Render tier)

There is no worker process. `run_recovery_sweeper()` is an asyncio task that
starts in the FastAPI lifespan:

1. **On startup** it runs one catch-up sweep straight away.
2. After that it sweeps every `RECOVERY_SWEEP_SECONDS` (default 900). A value
   of `0` keeps only the startup sweep.

Every pending action is stored on the case as `next_action_at`, so a sweep
just does whatever is due. On Render's free tier the instance sleeps after
about 15 minutes idle, and the loop doesn't run while it sleeps. **On the next
cold start the startup sweep sends whatever fell due while it was asleep.**
The next deadline is counted from when a reminder was actually sent. A long
sleep therefore delays the schedule but never sends several reminders at
once.

Each action is claimed first with a conditional update on the exact state
that was read (`status`, `reminder_count`, `next_action_at`), and the message
is sent only after that. Two instances or overlapping sweeps can therefore
never double-send. If you want reminders on time even when there is no
traffic, a free external pinger can hit `/api/health` every 10–14 minutes.

## Counting

* **Admin** (`GET /api/admin/stats` → `recovery`) shows, as counts only:
  * total scans
  * finder contacts
  * owner-confirmed recoveries
  * probable (unconfirmed)
  * owner said not found
  * awaiting owner
  * legacy manual "found"
  * `recovery_rate = confirmed ÷ finder contacts`
* Confirmed and probable are **never summed**.
* **Public counter** (`/api/public/stats` → `items_recovered`) counts
  owner-confirmed cases plus tags that owners manually set to `status=found`
  (legacy). A tag that is in both groups is counted once. Probable cases are
  never included.
* **14-day trend:** each row of `/api/admin/scans/daily` now also has
  `recovered`, the number of owner-confirmed recoveries by `resolved_at` day.
  The admin chart draws this as a line over the scan bars.

## Environment

* `RECOVERY_SWEEP_SECONDS` is optional (default 900).
* `SITE_URL`, which already exists, should be set in production so that
  reminder links are absolute. As a fallback, the origin of the finder's
  request is remembered on the case.

## Event Mode tags

* Scans of **registered** event tags open or attach to a case. Unregistered
  stickers have no owner and no database row, so they don't.
* Event guests have no account. Owners are loaded through
  `load_owner()` + `alert_profile()`, which means:
  * Guests get the confirmation link by email, and by WhatsApp only while
    their free 24-hour window is open.
  * Guests **never** get paid templates or SMS, even for urgent alerts.
  * Guest messages contain no dashboard hint.
* An organiser's help-desk **Mark returned** is **not** an owner
  confirmation. It doesn't confirm a case, and event tags are excluded from
  the public "legacy manual found" count.
* A guest's own **"I got my item back"** on their private Digital ID link
  *is* the owner. It confirms the tag's open case
  (`resolution_source = owner_digital_id`), but only if a finder actually
  reached out. Otherwise nothing is counted.
* Admin "total scans" comes from the `scans` collection. Event tags keep
  their own per-event scan counters (`events.stats`), so event scans show on
  the event page rather than in that total.
