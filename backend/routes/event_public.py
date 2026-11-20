"""Public Event Mode pages — server-rendered, no JS required, light on 2G/3G.

GET  /t/{token}            scan target printed in every QR (also /T/ — QR
                           payloads are upper-case for alphanumeric mode)
POST /t/{token}/claim      no-login claim (< 30 s): name, contact, item, mode
GET  /c/{code}  /c?code=   typed short code (PK24-0137-7QX2) → same page
GET  /e/{code}             event page (target of the shared poster QR)
GET  /id/{token}           Digital ID — show on screen, save as image or
                           phone lock-screen wallpaper, share, or print
POST /id/{token}/returned  owner (with manage key) marks the item returned
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import event_service as es
import ratelimit
from auth import get_current_user
from db import get_db
from notifications import notify_owner_background, whatsapp_business_number
from owners import alert_profile, load_owner
from print_engine import CAPTION, qr_matrix
from routes.finder_ssr import _resolve_lang, esc, render_claimed, render_layout, render_not_found
from routes.tag_routes import build_contact_block
from urls import resolve_site_url

router = APIRouter(tags=["event-public"])

# ---------------------------------------------------------------------------
# Strings (Hindi + English; other languages fall back to English)
# ---------------------------------------------------------------------------
E: dict[str, dict[str, str]] = {
    "en": {
        "claim_title": "Is this your sticker?",
        "claim_sub": "Register it in 30 seconds — no app, no sign-up. If it is ever lost, the finder can reach you without seeing your number.",
        "pack_note": "This is a guest pack: all {n} tags will be linked to you with one claim.",
        "your_name": "Your name",
        "mobile": "Mobile number (for WhatsApp alerts)",
        "email": "Email (optional)",
        "need_contact": "Give a mobile number or an email so we can alert you.",
        "item_on": "What is this sticker on?",
        "phone": "Phone", "bag": "Bag", "bottle": "Bottle", "other": "Other",
        "mode": "If someone finds it",
        "masked": "Keep my number private (recommended)",
        "direct": "Show my number so the finder can call me",
        "wa_opt": "Send me alerts on WhatsApp",
        "consent": "I agree Info-Tag stores my name and contact only to return my lost items.",
        "claim_btn": "Register my sticker",
        "found_title": "Found someone's item?",
        "found_body": "This sticker isn't registered yet, so its owner can't be reached here. Please hand the item to the event help desk.",
        "event_page": "Event lost & found page",
        "done": "Done! Your tags are active.",
        "done_sub": "If anyone scans them, you'll be alerted. Your number stays private.",
        "wa_btn": "Turn on WhatsApp alerts",
        "wa_hint": "Tap, then press Send in WhatsApp. This switches on free alerts.",
        "email_hint": "We'll alert you by email.",
        "no_channel": "Tip: add a mobile number or email so you can be alerted.",
        "wa_unavailable": "WhatsApp alerts aren't switched on for this event yet. Add an email to get alerts — or if you lose something, visit the help desk with your code.",
        "digital_id": "Open my Digital ID",
        "save_link": "Save this page — the Digital ID link lets you manage your tag.",
        "already": "This sticker is already registered.",
        "revoked_title": "This tag is no longer active",
        "revoked_body": "Please hand the item to the event help desk.",
        "closed_title": "Registration is closed for this event",
        "invalid_phone": "Please enter a valid mobile number.",
        "invalid_email": "Please enter a valid email.",
        "need_name": "Please enter your name.",
        "need_consent": "Please tick the consent box.",
        "direct_needs_phone": "To show your number, please enter it.",
        "slow_down": "Too many attempts — please wait a minute and try again.",
        "enter_code": "Type the code printed under the QR",
        "go": "Open",
        "code_not_found": "No tag found with that code. Check the letters and try again.",
        "ev_found": "Found something with an Info-Tag sticker?",
        "ev_found_body": "Scan the sticker with your phone camera — the owner is alerted instantly. No camera? Type its code:",
        "ev_lost": "Lost something?",
        "ev_lost_body": "If your item had an Info-Tag sticker, whoever finds it can reach you. You can also visit the help desk.",
        "ev_claim": "Have a new sticker? Scan it to register it in 30 seconds.",
        "id_title": "Digital ID",
        "id_dl_card": "Save card image",
        "id_dl_wall": "Save as phone wallpaper",
        "id_wall_hint": "Set it as your lock screen: if your phone is lost, the finder can scan it.",
        "id_share": "Share",
        "id_print": "Print",
        "id_claim": "Register this tag",
        "id_returned": "I got my item back",
        "id_returned_done": "Marked as returned — thank you!",
        "holder": "Holder",
        "status_unclaimed": "Not registered yet",
        "status_active": "Active",
        "status_returned": "Returned to owner",
        "status_revoked": "Inactive",
    },
    "hi": {
        "claim_title": "क्या यह स्टिकर आपका है?",
        "claim_sub": "30 सेकंड में रजिस्टर करें — कोई ऐप या साइन-अप नहीं। सामान खोने पर मिलने वाला आपका नंबर देखे बिना आप तक पहुँच सकेगा।",
        "pack_note": "यह गेस्ट पैक है: एक बार में सभी {n} टैग आपसे जुड़ जाएँगे।",
        "your_name": "आपका नाम",
        "mobile": "मोबाइल नंबर (WhatsApp अलर्ट के लिए)",
        "email": "ईमेल (वैकल्पिक)",
        "need_contact": "अलर्ट के लिए मोबाइल नंबर या ईमेल दें।",
        "item_on": "यह स्टिकर किस पर लगा है?",
        "phone": "फ़ोन", "bag": "बैग", "bottle": "बोतल", "other": "अन्य",
        "mode": "अगर किसी को मिले तो",
        "masked": "मेरा नंबर छिपा रहे (सुझाया गया)",
        "direct": "मेरा नंबर दिखाएँ ताकि वह मुझे कॉल कर सके",
        "wa_opt": "मुझे WhatsApp पर अलर्ट भेजें",
        "consent": "मैं सहमत हूँ कि Info-Tag मेरा नाम और संपर्क सिर्फ़ खोया सामान लौटाने के लिए रखे।",
        "claim_btn": "मेरा स्टिकर रजिस्टर करें",
        "found_title": "किसी और का सामान मिला?",
        "found_body": "यह स्टिकर अभी रजिस्टर नहीं है, इसलिए मालिक से यहाँ संपर्क नहीं हो सकता। कृपया सामान इवेंट हेल्प डेस्क पर जमा करें।",
        "event_page": "इवेंट खोया-पाया पेज",
        "done": "हो गया! आपके टैग चालू हैं।",
        "done_sub": "कोई इन्हें स्कैन करेगा तो आपको अलर्ट मिलेगा। आपका नंबर छिपा रहेगा।",
        "wa_btn": "WhatsApp अलर्ट चालू करें",
        "wa_hint": "टैप करें, फिर WhatsApp में Send दबाएँ। इससे मुफ़्त अलर्ट चालू हो जाएँगे।",
        "email_hint": "हम आपको ईमेल से अलर्ट करेंगे।",
        "no_channel": "सुझाव: अलर्ट पाने के लिए मोबाइल नंबर या ईमेल जोड़ें।",
        "wa_unavailable": "इस इवेंट के लिए WhatsApp अलर्ट अभी चालू नहीं हैं। अलर्ट के लिए ईमेल जोड़ें — या कुछ खोने पर अपने कोड के साथ हेल्प डेस्क पर जाएँ।",
        "digital_id": "मेरी डिजिटल ID खोलें",
        "save_link": "यह पेज सेव करें — डिजिटल ID लिंक से आप अपना टैग संभाल सकते हैं।",
        "already": "यह स्टिकर पहले से रजिस्टर है।",
        "revoked_title": "यह टैग अब सक्रिय नहीं है",
        "revoked_body": "कृपया सामान इवेंट हेल्प डेस्क पर जमा करें।",
        "closed_title": "इस इवेंट के लिए रजिस्ट्रेशन बंद है",
        "invalid_phone": "कृपया सही मोबाइल नंबर डालें।",
        "invalid_email": "कृपया सही ईमेल डालें।",
        "need_name": "कृपया अपना नाम लिखें।",
        "need_consent": "कृपया सहमति वाला बॉक्स चुनें।",
        "direct_needs_phone": "नंबर दिखाने के लिए कृपया नंबर डालें।",
        "slow_down": "बहुत ज़्यादा कोशिशें — एक मिनट बाद फिर कोशिश करें।",
        "enter_code": "QR के नीचे छपा कोड लिखें",
        "go": "खोलें",
        "code_not_found": "इस कोड का कोई टैग नहीं मिला। अक्षर जाँचकर फिर कोशिश करें।",
        "ev_found": "Info-Tag स्टिकर वाला सामान मिला?",
        "ev_found_body": "फ़ोन कैमरे से स्टिकर स्कैन करें — मालिक को तुरंत अलर्ट जाएगा। कैमरा नहीं? कोड लिखें:",
        "ev_lost": "कुछ खो गया?",
        "ev_lost_body": "अगर आपके सामान पर Info-Tag स्टिकर था, तो मिलने वाला आपसे संपर्क कर सकता है। आप हेल्प डेस्क पर भी जा सकते हैं।",
        "ev_claim": "नया स्टिकर मिला है? 30 सेकंड में रजिस्टर करने के लिए उसे स्कैन करें।",
        "id_title": "डिजिटल ID",
        "id_dl_card": "कार्ड इमेज सेव करें",
        "id_dl_wall": "फ़ोन वॉलपेपर के रूप में सेव करें",
        "id_wall_hint": "इसे लॉक-स्क्रीन बनाएँ: फ़ोन खोने पर मिलने वाला इसे स्कैन कर सकेगा।",
        "id_share": "शेयर करें",
        "id_print": "प्रिंट करें",
        "id_claim": "यह टैग रजिस्टर करें",
        "id_returned": "मेरा सामान मिल गया",
        "id_returned_done": "लौटाया गया दर्ज हुआ — धन्यवाद!",
        "holder": "धारक",
        "status_unclaimed": "अभी रजिस्टर नहीं",
        "status_active": "सक्रिय",
        "status_returned": "मालिक को लौटाया गया",
        "status_revoked": "निष्क्रिय",
    },
}

EXTRA_CSS = """
<style>
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 12px}
.chips label{display:inline-flex;align-items:center;gap:6px;border:1px solid #d4d4d4;border-radius:9999px;padding:9px 14px;font-weight:600;cursor:pointer}
.chips label:has(input:checked){background:#0F172A;color:#fff;border-color:#0F172A}
.chips input{margin:0}
.radio{display:flex;gap:8px;align-items:flex-start;margin:6px 0;font-size:14px}
.radio input,.check input{width:auto;margin:3px 0 0}
.check{display:flex;gap:8px;align-items:flex-start;font-size:14px;margin:8px 0}
.err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;border-radius:8px;padding:10px;margin-bottom:12px;font-size:14px}
.codes{font-family:ui-monospace,monospace;font-size:15px;font-weight:700;letter-spacing:.03em}
.idcard{max-width:360px;margin:0 auto}
.idcard svg{width:100%;height:auto;display:block;border-radius:16px;box-shadow:0 6px 24px rgba(0,0,0,.12)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
@media print{header,footer,.noprint{display:none!important}.card{border:none}.idcard{max-width:86mm}}
</style>"""


def tt(lang: str, key: str) -> str:
    return E.get(lang, E["en"]).get(key) or E["en"].get(key, key)


def _page(lang: str, body: str, title: str) -> str:
    return render_layout(lang=lang, body=EXTRA_CSS + body, title=title)


def _html(content: str, request: Request, status: int = 200) -> HTMLResponse:
    resp = HTMLResponse(content, status_code=status)
    ratelimit.ensure_client_cookie(request, resp)
    return resp


def _lang(request: Request, event: Optional[dict] = None, override: Optional[str] = None) -> str:
    if override or request.query_params.get("lang") or request.headers.get("accept-language"):
        return _resolve_lang(request, override)
    return (event or {}).get("default_lang") or _resolve_lang(request)


def _message_card(lang: str, title: str, body: str, event: Optional[dict] = None, testid: str = "event-message") -> str:
    help_note = esc((event or {}).get("help_desk_note", ""))
    link = f'<a class="btn" href="/e/{esc(event["code"])}">{esc(tt(lang, "event_page"))}<span class="arrow">→</span></a>' if event else ""
    return f"""<div class="card" data-testid="{testid}" style="text-align:center">
<h1>{esc(title)}</h1><p class="muted">{esc(body)}</p>{f'<p><b>{help_note}</b></p>' if help_note else ''}{link}</div>"""


# ---------------------------------------------------------------------------
# Scan → claim or finder page
# ---------------------------------------------------------------------------
async def _count_scan(db, request: Request, res: es.Resolved) -> None:
    who = ratelimit.client_id(request) or ratelimit.client_ip_hash(request)
    if not ratelimit.first_seen(f"scan:{res.batch['bid']}:{res.serial}:{who}", 60):
        return
    await es.bump(db, res.event["id"], scans=1)
    if res.tag:
        await db.tags.update_one({"id": res.tag["id"]}, {"$inc": {"scan_count": 1}, "$set": {"last_scan_at": es.utcnow()}})


def _claim_form(lang: str, res: es.Resolved, error: str = "", v: Optional[dict] = None) -> str:
    v = v or {}
    ev = res.event
    pack = int(res.batch.get("pack_size") or 1)
    item = v.get("item_type") or "other"
    mode = v.get("contact_mode") or ev.get("default_contact_mode") or "masked"
    chips = "".join(
        f'<label><input type="radio" name="item_type" value="{k}"{" checked" if k == item else ""}>{esc(tt(lang, k))}</label>'
        for k in es.ITEM_TYPES
    )
    err = f'<div class="err" data-testid="claim-error">{esc(error)}</div>' if error else ""
    pack_html = f'<p class="muted">{esc(tt(lang, "pack_note").format(n=pack))}</p>' if pack > 1 else ""
    wa_checked = "" if v and not v.get("wa_opt_in") else " checked"
    return f"""
<div class="card" data-testid="event-claim">
<div class="kicker">{esc(ev['name'])}</div>
<h1>{esc(tt(lang, 'claim_title'))}</h1>
<p class="muted">{esc(tt(lang, 'claim_sub'))}</p>
<p class="codes">{esc(res.code)}</p>
{pack_html}{err}
<form method="post" action="/t/{esc(res.token)}/claim" data-testid="claim-form">
<input type="hidden" name="lang" value="{esc(lang)}">
<input name="name" placeholder="{esc(tt(lang, 'your_name'))}" required maxlength="80" autocomplete="name" value="{esc(v.get('name', ''))}" data-testid="claim-name">
<input name="phone" type="tel" inputmode="tel" placeholder="{esc(tt(lang, 'mobile'))}" maxlength="20" autocomplete="tel" value="{esc(v.get('phone', ''))}" data-testid="claim-phone">
<input name="email" type="email" placeholder="{esc(tt(lang, 'email'))}" maxlength="160" autocomplete="email" value="{esc(v.get('email', ''))}" data-testid="claim-email">
<div class="kicker" style="margin-top:6px">{esc(tt(lang, 'item_on'))}</div>
<div class="chips" data-testid="claim-items">{chips}</div>
<div class="kicker">{esc(tt(lang, 'mode'))}</div>
<label class="radio"><input type="radio" name="contact_mode" value="masked"{" checked" if mode != "direct" else ""}>{esc(tt(lang, 'masked'))}</label>
<label class="radio"><input type="radio" name="contact_mode" value="direct"{" checked" if mode == "direct" else ""}>{esc(tt(lang, 'direct'))}</label>
<label class="check"><input type="checkbox" name="wa_opt_in" value="1"{wa_checked}>{esc(tt(lang, 'wa_opt'))}</label>
<label class="check"><input type="checkbox" name="consent" value="1" required data-testid="claim-consent">{esc(tt(lang, 'consent'))}</label>
<input type="text" name="bot_check" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
<button class="btn-primary" type="submit" style="width:100%;margin-top:8px" data-testid="claim-submit">{esc(tt(lang, 'claim_btn'))}</button>
</form>
</div>
<div class="card">
<h2 style="margin-top:0">{esc(tt(lang, 'found_title'))}</h2>
<p class="muted">{esc(tt(lang, 'found_body'))}</p>
{f'<p><b>{esc(ev.get("help_desk_note", ""))}</b></p>' if ev.get('help_desk_note') else ''}
<a class="btn" href="/e/{esc(ev['code'])}">{esc(tt(lang, 'event_page'))}<span class="arrow">→</span></a>
</div>"""


async def _render_tag(db, request: Request, res: es.Resolved, lang: str) -> HTMLResponse:
    await _count_scan(db, request, res)
    if res.revoked:
        return _html(_page(lang, _message_card(lang, tt(lang, "revoked_title"), tt(lang, "revoked_body"), res.event, "event-revoked"), "Info-Tag"), request, 410)
    if res.tag:
        contact = await build_contact_block(db, res.tag)
        return _html(render_claimed(lang, res.tag, contact), request)
    if not res.event.get("claims_open", True):
        return _html(_page(lang, _message_card(lang, tt(lang, "closed_title"), tt(lang, "found_body"), res.event), "Info-Tag"), request)
    return _html(_page(lang, _claim_form(lang, res), tt(lang, "claim_title")), request)


async def _legacy_slug(db, value: str) -> Optional[RedirectResponse]:
    """Old QR codes / typed slugs keep working through the new short paths."""
    if await db.tags.find_one({"slug": value}, {"_id": 1}):
        return RedirectResponse(f"/api/finder/{quote(value)}", status_code=302)
    return None


@router.get("/t/{token}", response_class=HTMLResponse)
@router.get("/T/{token}", response_class=HTMLResponse, include_in_schema=False)
async def scan_tag(token: str, request: Request):
    db = get_db()
    res = await es.resolve_token(db, token)
    if not res:
        legacy = await _legacy_slug(db, token)
        if legacy:
            return legacy
        lang = _lang(request)
        return _html(render_not_found(lang), request, 404)
    return await _render_tag(db, request, res, _lang(request, res.event))


@router.get("/c", response_class=HTMLResponse)
@router.get("/c/{code}", response_class=HTMLResponse)
async def by_code(request: Request, code: str = ""):
    db = get_db()
    code = code or request.query_params.get("code", "")
    res = await es.resolve_code(db, code) if code else None
    if res:
        lang = request.query_params.get("lang")
        suffix = f"?lang={quote(lang)}" if lang else ""
        return RedirectResponse(f"/t/{res.token}{suffix}", status_code=302)
    legacy = await _legacy_slug(db, code.strip()) if code else None
    if legacy:
        return legacy
    lang = _lang(request)
    ev_code = (request.query_params.get("event") or "").upper()
    ev = await db.events.find_one({"code": ev_code}, {"_id": 0}) if ev_code else None
    body = _message_card(lang, tt(lang, "code_not_found"), "", ev, "code-not-found") + _code_form(lang, ev_code)
    return _html(_page(lang, body, "Info-Tag"), request, 404)


def _code_form(lang: str, ev_code: str = "") -> str:
    return f"""<form method="get" action="/c" class="card" data-testid="code-form">
<label class="kicker" for="code">{esc(tt(lang, 'enter_code'))}</label>
<input id="code" name="code" placeholder="{esc(ev_code or 'PK24')}-0001-ABCD" autocapitalize="characters" autocomplete="off" required>
<input type="hidden" name="event" value="{esc(ev_code)}"><input type="hidden" name="lang" value="{esc(lang)}">
<button class="btn-primary" type="submit" style="width:100%">{esc(tt(lang, 'go'))}</button></form>"""


_PHONE_STRIP = re.compile(r"[^+\d]")
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[A-Za-z]{2,}$")


def _clean_text(s: str, n: int) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()[:n]


async def _optional_user(request: Request) -> Optional[dict]:
    try:
        user = await get_current_user(request, get_db())
    except Exception:  # noqa: BLE001 — anonymous is the normal case
        return None
    return user if user.get("role") in ("user", "admin", "organizer") else None


@router.post("/t/{token}/claim", response_class=HTMLResponse)
@router.post("/T/{token}/claim", response_class=HTMLResponse, include_in_schema=False)
async def claim(
    token: str,
    request: Request,
    name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    item_type: str = Form("other"),
    contact_mode: str = Form("masked"),
    wa_opt_in: str = Form(""),
    consent: str = Form(""),
    lang: str = Form(""),
    bot_check: str = Form(""),
):
    db = get_db()
    res = await es.resolve_token(db, token)
    lang = _lang(request, res.event if res else None, lang or None)
    if not res:
        return _html(render_not_found(lang), request, 404)
    if bot_check:  # honeypot — look successful, do nothing
        return _html(_page(lang, _message_card(lang, tt(lang, "done"), tt(lang, "done_sub")), "Info-Tag"), request)
    if res.revoked or res.tag or not res.event.get("claims_open", True):
        return await _render_tag(db, request, res, lang)

    values = {"name": name, "phone": phone, "email": email, "item_type": item_type, "contact_mode": contact_mode, "wa_opt_in": bool(wa_opt_in)}
    # NAT-friendly limits: strict per phone (cookie), generous per event / IP.
    if not ratelimit.check(
        request, "claim", per_client=(10, 600), per_ip=(400, 600),
        scope=res.event["id"], per_scope=(1200, 60),
    ):
        return _html(_page(lang, _claim_form(lang, res, tt(lang, "slow_down"), values), "Info-Tag"), request, 429)

    name_c = _clean_text(name, 80)
    phone_c = _PHONE_STRIP.sub("", phone or "")
    email_c = (email or "").strip()[:160]
    error = ""
    if not name_c:
        error = tt(lang, "need_name")
    elif phone_c and len(phone_c.lstrip("+")) < 8:
        error = tt(lang, "invalid_phone")
    elif email_c and not _EMAIL_RE.match(email_c):
        error = tt(lang, "invalid_email")
    elif not phone_c and not email_c:
        error = tt(lang, "need_contact")
    elif contact_mode == "direct" and not phone_c:
        error = tt(lang, "direct_needs_phone")
    elif not consent:
        error = tt(lang, "need_consent")
    if error:
        return _html(_page(lang, _claim_form(lang, res, error, values), tt(lang, "claim_title")), request, 400)
    if phone_c and not phone_c.startswith("+") and len(phone_c) == 10:
        phone_c = "+91" + phone_c  # Indian mobile typed without country code
    item = item_type if item_type in es.ITEM_TYPES else "other"
    mode = "direct" if contact_mode == "direct" else "masked"

    manage_key = es.new_manage_key()
    user = await _optional_user(request)
    if user and user.get("role") == "user":
        owner_id = user["id"]  # signed-in owners see event tags on their dashboard
        if phone_c and not user.get("phone"):
            await db.users.update_one({"id": owner_id}, {"$set": {"phone": phone_c}})
    else:
        guest = await es.create_guest_owner(
            db, name=name_c, phone=phone_c, email=email_c, wa_opt_in=bool(wa_opt_in),
            lang=lang, event=res.event, manage_key=manage_key,
        )
        owner_id = guest["id"]
    try:
        docs = await es.claim_pack(db, res, owner_id=owner_id, item_type=item, contact_mode=mode, manage_key=manage_key)
    except es.AlreadyClaimed:
        if owner_id.startswith("guest_"):
            await db.guest_owners.delete_one({"id": owner_id})
        body = _message_card(lang, tt(lang, "already"), "", res.event)
        return _html(_page(lang, body, "Info-Tag"), request, 409)

    base = resolve_site_url(request)
    id_link = f"{base}/id/{res.token}?k={manage_key}"
    codes = "\n".join(f"{d['slug']} — {d['label']}" for d in docs)
    # One confirmation per claim (not per tag).  E-mail now; WhatsApp only once
    # the owner messages us (that opens Meta's free window — never a paid send).
    owner = await load_owner(db, owner_id)
    if owner and owner.get("email"):
        notify_owner_background(
            {**alert_profile(owner), "whatsapp_alerts": False, "sms_alerts": False},
            f"[Info-Tag] Your {res.event['name']} tags are active",
            f"Hi {name_c},\n\nYour Info-Tag stickers are registered:\n{codes}\n\n"
            f"If someone finds your item and scans the sticker, we'll alert you.\n"
            f"Your Digital ID (keep this link private): {id_link}\n",
        )
    return _html(_page(lang, _success(lang, res, docs, phone_c, email_c, bool(wa_opt_in), id_link), tt(lang, "done")), request)


def _success(lang: str, res: es.Resolved, docs: list[dict], phone: str, email: str, wa_opt_in: bool, id_link: str) -> str:
    biz = whatsapp_business_number()
    codes = "".join(f'<div class="codes">{esc(d["slug"])} <span class="muted">{esc(d["label"])}</span></div>' for d in docs)
    wa = ""
    if biz and phone and wa_opt_in:
        href = f"https://wa.me/{biz.lstrip('+')}?text={quote('START ' + res.code)}"
        wa = f"""<a class="btn-contact btn-wa" href="{esc(href)}" rel="noopener" data-testid="claim-wa-optin">💬 {esc(tt(lang, 'wa_btn'))}</a>
<p class="muted" style="margin-top:0">{esc(tt(lang, 'wa_hint'))}</p>"""
    elif email:
        wa = f'<p class="muted">✉️ {esc(tt(lang, "email_hint"))}</p>'
    elif phone:
        wa = f'<p class="muted">{esc(tt(lang, "wa_unavailable"))}</p>'
    else:
        wa = f'<p class="muted">{esc(tt(lang, "no_channel"))}</p>'
    return f"""
<div class="card" data-testid="claim-success">
<div class="thanks"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
<h1 style="color:inherit">{esc(tt(lang, 'done'))}</h1></div>
<p class="muted" style="text-align:center">{esc(tt(lang, 'done_sub'))}</p>
{codes}
<div style="margin-top:14px">{wa}</div>
<a class="btn-primary" style="display:flex;text-decoration:none;margin-top:8px" href="{esc(id_link)}" data-testid="claim-digital-id">🪪 {esc(tt(lang, 'digital_id'))}</a>
<p class="muted">{esc(tt(lang, 'save_link'))}</p>
</div>"""


# ---------------------------------------------------------------------------
# Event page (poster QR target)
# ---------------------------------------------------------------------------
@router.get("/e/{code}", response_class=HTMLResponse)
@router.get("/E/{code}", response_class=HTMLResponse, include_in_schema=False)
async def event_page(code: str, request: Request):
    db = get_db()
    ev = await db.events.find_one({"code": code.upper()}, {"_id": 0})
    if not ev:
        return _html(render_not_found(_lang(request)), request, 404)
    lang = _lang(request, ev)
    meta = " · ".join(x for x in (ev.get("date"), ev.get("venue")) if x)
    help_note = ev.get("help_desk_note", "")
    body = f"""
<div class="card" data-testid="event-page">
<div class="kicker">Info-Tag</div>
<h1>{esc(ev['name'])}</h1>
{f'<p class="muted">{esc(meta)}</p>' if meta else ''}
{f'<div class="reward">🧭 {esc(help_note)}</div>' if help_note else ''}
</div>
<div class="card"><h2 style="margin-top:0">{esc(tt(lang, 'ev_found'))}</h2>
<p class="muted">{esc(tt(lang, 'ev_found_body'))}</p></div>
{_code_form(lang, ev['code'])}
<div class="card"><h2 style="margin-top:0">{esc(tt(lang, 'ev_lost'))}</h2>
<p class="muted">{esc(tt(lang, 'ev_lost_body'))}</p>
<p class="muted">{esc(tt(lang, 'ev_claim'))}</p></div>"""
    return _html(_page(lang, body, ev["name"]), request)


# ---------------------------------------------------------------------------
# Digital ID
# ---------------------------------------------------------------------------
def qr_svg_path(data: str) -> tuple[str, int]:
    m = qr_matrix(data)
    parts = []
    for r, row in enumerate(m):
        c = 0
        n = len(row)
        while c < n:
            if row[c]:
                s = c
                while c < n and row[c]:
                    c += 1
                parts.append(f"M{s} {r}h{c - s}v1h-{c - s}z")
            else:
                c += 1
    return "".join(parts), len(m)


def _svg_text(x: float, y: float, text: str, size: float, weight: int = 700, fill: str = "#000", anchor: str = "middle") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
            f'font-family="Noto Sans Devanagari, Noto Sans, system-ui, sans-serif">{esc(text)}</text>')


def digital_id_svg(*, qr_data: str, event_name: str, code: str, holder: str, item: str, status: str, w: int = 540, h: int = 860, wallpaper: bool = False) -> str:
    path, n = qr_svg_path(qr_data)
    qr_px = int(w * 0.62)
    quiet = qr_px * 4 / n
    qx, qy = (w - qr_px) / 2, (h * 0.42 if wallpaper else 170)
    band = 120 if not wallpaper else int(h * 0.12)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
        f'<rect width="{w}" height="{h}" rx="{0 if wallpaper else 28}" fill="#fff"/>',
        f'<rect width="{w}" height="{band}" rx="{0 if wallpaper else 28}" fill="#0F172A"/>',
        f'<rect y="{band - 30}" width="{w}" height="30" fill="#0F172A"/>' if not wallpaper else "",
        _svg_text(w / 2, band * 0.45, "Info-Tag", band * 0.18, 900, "#E25822"),
        _svg_text(w / 2, band * 0.78, event_name[:40], band * 0.2, 700, "#fff"),
        f'<rect x="{qx - quiet}" y="{qy - quiet}" width="{qr_px + 2 * quiet}" height="{qr_px + 2 * quiet}" fill="#fff"/>',
        f'<g transform="translate({qx} {qy}) scale({qr_px / n})"><path d="{path}" fill="#000" shape-rendering="crispEdges"/></g>',
    ]
    y = qy + qr_px + quiet + 42
    parts.append(_svg_text(w / 2, y, code, 34 if not wallpaper else 54, 800))
    parts.append(_svg_text(w / 2, y + (40 if not wallpaper else 64), CAPTION, 26 if not wallpaper else 42, 700, "#111"))
    if holder:
        parts.append(_svg_text(w / 2, y + (86 if not wallpaper else 140), holder[:32], 28 if not wallpaper else 46, 700, "#0F172A"))
    if item:
        parts.append(_svg_text(w / 2, y + (122 if not wallpaper else 196), item, 22 if not wallpaper else 36, 500, "#444"))
    if not wallpaper:
        parts.append(_svg_text(w / 2, h - 28, status, 20, 600, "#666"))
    parts.append("</svg>")
    return "".join(parts)


async def _manage_ok(db, res: es.Resolved, k: str) -> bool:
    if not k or not res.tag:
        return False
    claim_doc = await db.claims.find_one({"_id": res.tag.get("claim_id")}, {"_id": 0, "manage_hash": 1})
    return bool(claim_doc) and claim_doc.get("manage_hash") == es.hash_key(k)


@router.get("/id/{token}", response_class=HTMLResponse)
async def digital_id(token: str, request: Request, k: str = "", done: str = ""):
    db = get_db()
    res = await es.resolve_token(db, token)
    if not res:
        return _html(render_not_found(_lang(request)), request, 404)
    lang = _lang(request, res.event)
    owner_view = await _manage_ok(db, res, k)
    holder = ""
    if owner_view:
        owner = await load_owner(db, res.tag.get("owner_id"))
        holder = (owner or {}).get("display_name", "")
    if res.revoked:
        status = tt(lang, "status_revoked")
    elif not res.tag:
        status = tt(lang, "status_unclaimed")
    elif res.tag.get("event_status") == "returned":
        status = tt(lang, "status_returned")
    else:
        status = tt(lang, "status_active")
    item = (res.tag or {}).get("label", "") if res.tag else ""
    from tokens import qr_url

    qr_data = qr_url(os_qr_base(request), res.token)
    card = digital_id_svg(qr_data=qr_data, event_name=res.event["name"], code=res.code, holder=holder, item=item, status=status)
    wall = digital_id_svg(qr_data=qr_data, event_name=res.event["name"], code=res.code, holder=holder, item=item, status=status, w=1080, h=2340, wallpaper=True)
    share_url = f"{resolve_site_url(request)}/id/{res.token}"
    actions = []
    if not res.tag and not res.revoked:
        actions.append(f'<a class="btn-primary" style="display:flex;text-decoration:none" href="/t/{esc(res.token)}" data-testid="id-claim">{esc(tt(lang, "id_claim"))}</a>')
    if owner_view and res.tag.get("event_status") != "returned":
        actions.append(f"""<form method="post" action="/id/{esc(res.token)}/returned"><input type="hidden" name="k" value="{esc(k)}">
<button class="btn" type="submit" data-testid="id-returned">✅ {esc(tt(lang, 'id_returned'))}<span class="arrow">→</span></button></form>""")
    done_html = f'<div class="privacy-note" data-testid="id-returned-done">✅ {esc(tt(lang, "id_returned_done"))}</div>' if done else ""
    body = f"""
<div class="card noprint" style="text-align:center"><div class="kicker">{esc(tt(lang, 'id_title'))}</div></div>
{done_html}
<div class="idcard" id="idcard" data-testid="digital-id-card">{card}</div>
<template id="wall">{wall}</template>
<div class="card noprint">
<div class="row2">
<button class="btn js-only" type="button" onclick="itPng('idcard-svg',540,860,'{esc(res.code)}-id.png')" data-testid="id-dl-card">🖼️ {esc(tt(lang, 'id_dl_card'))}</button>
<button class="btn js-only" type="button" onclick="itPng('wall-svg',1080,2340,'{esc(res.code)}-wallpaper.png')" data-testid="id-dl-wall">📱 {esc(tt(lang, 'id_dl_wall'))}</button>
<button class="btn js-only" type="button" onclick="itShare()" data-testid="id-share">🔗 {esc(tt(lang, 'id_share'))}</button>
<button class="btn" type="button" onclick="window.print()" data-testid="id-print">🖨️ {esc(tt(lang, 'id_print'))}</button>
</div>
<p class="muted">{esc(tt(lang, 'id_wall_hint'))}</p>
{''.join(actions)}
</div>
<script>
(function(){{var c=document.querySelector('#idcard svg');if(c)c.id='idcard-svg';
var t=document.getElementById('wall');if(t){{var d=document.createElement('div');d.style.display='none';d.innerHTML=t.innerHTML;document.body.appendChild(d);d.firstChild.id='wall-svg';}}}})();
function itPng(id,w,h,name){{var s=document.getElementById(id);var x=new XMLSerializer().serializeToString(s);
var img=new Image();img.onload=function(){{var cv=document.createElement('canvas');cv.width=w;cv.height=h;var g=cv.getContext('2d');
g.fillStyle='#fff';g.fillRect(0,0,w,h);g.drawImage(img,0,0,w,h);cv.toBlob(function(b){{var a=document.createElement('a');
a.href=URL.createObjectURL(b);a.download=name;document.body.appendChild(a);a.click();a.remove();}},'image/png');}};
img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(x);}}
function itShare(){{var u={_js_str(share_url)};if(navigator.share){{navigator.share({{title:'Info-Tag',url:u}}).catch(function(){{}});}}
else{{location.href='https://wa.me/?text='+encodeURIComponent(u);}}}}
</script>"""
    resp = _html(_page(lang, body, tt(lang, "id_title")), request)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


def _js_str(s: str) -> str:
    import json

    return json.dumps(s).replace("<", "\\u003c")


def os_qr_base(request: Request) -> str:
    import os

    return os.environ.get("TAG_QR_BASE", "").strip().rstrip("/") or resolve_site_url(request)


@router.post("/id/{token}/returned")
async def digital_id_returned(token: str, request: Request, k: str = Form("")):
    db = get_db()
    res = await es.resolve_token(db, token)
    if not res or not await _manage_ok(db, res, k):
        return _html(render_not_found(_lang(request)), request, 404)
    if res.tag.get("event_status") != "returned":
        await db.tags.update_one({"id": res.tag["id"]}, {"$set": {"event_status": "returned", "status": "found", "returned_at": es.utcnow()}})
        await es.bump(db, res.event["id"], returned=1)
    return RedirectResponse(f"/id/{res.token}?k={quote(k)}&done=1", status_code=303)
