"""Server-side rendered finder page — the highest-impact privacy + perf win.

Why SSR here?
* The finder is the ONLY page a stranger ever sees, and we want it to load
  on slow 2G/3G with no JS at all.
* Total payload target: <75 KB gzipped. The React bundle alone is ~80 KB
  gzipped before any of our code — so we bypass it entirely.
* Forms POST natively; geolocation is the only progressive enhancement
  (a 600-byte inline script that gracefully degrades if disabled).

Routes
------
GET  /api/finder/{slug}            → full HTML finder page
POST /api/finder/{slug}/action     → handles the form, returns HTML response
"""
from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import hash_ip
from db import get_db
from notifications import notify_owner
from push import push_owner

router = APIRouter(prefix="/api/finder", tags=["finder-ssr"])


# ---------------------------------------------------------------------------
# Tiny i18n (server-side) — English + Hindi only; the SPA carries the rest.
# ---------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "header": "Hi, a kind person scanned this tag.",
        "owner_says": "The owner says",
        "quick_actions": "Quick actions",
        "wrong_parking": "Vehicle parked incorrectly",
        "headlight_on": "Headlights / lights left on",
        "found_share": "I found this — share my location",
        "send_message": "Send a message",
        "your_name": "Your name (optional)",
        "your_contact": "Your phone or email (optional)",
        "message_ph": "Type a short note for the owner…",
        "include_loc": "Attach my approximate location",
        "send": "Send",
        "sent_thanks": "Sent — thank you. The owner has been alerted.",
        "reported_lost": "This tag has been reported lost. Please help the owner.",
        "unclaimed_title": "This tag isn't claimed yet",
        "unclaimed_body": "If this tag belongs to you, sign in to claim it.",
        "tag_not_found": "We couldn't find this tag.",
        "tag_not_found_help": "The QR may have been misprinted, or this code isn't an Info-Tag.",
        "powered_by": "Powered by Info-Tag — privacy-first, no app needed.",
        "made_in_india": "Made in India",
        "lang_switch": "हिन्दी",
        "back": "← Back",
        "em_heading": "MEDICAL EMERGENCY ID",
        "em_blood": "Blood group",
        "em_allergies": "Allergies",
        "em_chronic": "Chronic conditions",
        "em_call": "Call emergency contact",
        "em_ps": "Nearest police station",
        "em_disclaimer": "Information shown with the owner's consent. Verify identity before treatment.",
        "verify_notice": "Please verify before acting on this information.",
        "last_updated": "Last updated",
        "contact_owner": "Contact the owner",
        "call_owner": "Call the owner",
        "whatsapp_owner": "WhatsApp the owner",
        "sms_owner": "SMS the owner",
        "request_callback": "Request a call back",
        "callback_hint": "Leave your number — the owner is alerted instantly and will call you. Their number stays private.",
        "your_phone": "Your phone number",
        "callback_send": "Alert the owner",
        "privacy_note": "Privacy-protected: the owner's phone number is never shown.",
        "wa_prefill": "Hi! I scanned your Info-Tag",
        "reward_offered": "Reward for returning this",
        "sp_heading": "PLEASE HELP ME",
        "sp_body": "I may not be able to speak or answer questions. Please be patient and kind with me.",
        "sp_guardian": "My guardian",
        "sp_call_guardian": "Call my guardian",
        "sp_notes": "Things to know about me",
        "sp_home": "I live near",
        "sp_thanks": "Thank you for stopping to help. It means everything.",
    },
    "hi": {
        "header": "नमस्ते, किसी ने यह टैग स्कैन किया है।",
        "owner_says": "मालिक का संदेश",
        "quick_actions": "त्वरित कार्य",
        "wrong_parking": "वाहन ग़लत जगह पार्क है",
        "headlight_on": "हेडलाइट / लाइटें चालू रह गई हैं",
        "found_share": "यह मुझे मिला — मेरी लोकेशन भेजें",
        "send_message": "संदेश भेजें",
        "your_name": "आपका नाम (वैकल्पिक)",
        "your_contact": "आपका फ़ोन/ईमेल (वैकल्पिक)",
        "message_ph": "मालिक के लिए एक छोटा संदेश…",
        "include_loc": "मेरी अनुमानित लोकेशन जोड़ें",
        "send": "भेजें",
        "sent_thanks": "भेज दिया — धन्यवाद। मालिक को सूचना मिल गई है।",
        "reported_lost": "यह टैग खोया हुआ बताया गया है। कृपया मदद करें।",
        "unclaimed_title": "यह टैग अभी क्लेम नहीं किया गया है",
        "unclaimed_body": "अगर यह आपका है, तो साइन इन करके इसे क्लेम करें।",
        "tag_not_found": "यह टैग नहीं मिला।",
        "tag_not_found_help": "QR ग़लत प्रिंट हुआ हो सकता है।",
        "powered_by": "Info-Tag — गोपनीयता-प्रथम, कोई ऐप नहीं।",
        "made_in_india": "मेड इन इंडिया",
        "lang_switch": "English",
        "back": "← वापस",
        "em_heading": "मेडिकल इमरजेंसी आईडी",
        "em_blood": "ब्लड ग्रुप",
        "em_allergies": "एलर्जी",
        "em_chronic": "पुरानी बीमारियाँ",
        "em_call": "इमरजेंसी संपर्क को कॉल करें",
        "em_ps": "नज़दीकी पुलिस स्टेशन",
        "em_disclaimer": "मालिक की सहमति से दिखाई गई जानकारी।",
        "verify_notice": "कार्य करने से पहले जानकारी जाँचें।",
        "last_updated": "आख़िरी बार अपडेट",
        "contact_owner": "मालिक से संपर्क करें",
        "call_owner": "मालिक को कॉल करें",
        "whatsapp_owner": "मालिक को WhatsApp करें",
        "sms_owner": "मालिक को SMS करें",
        "request_callback": "कॉल-बैक का अनुरोध करें",
        "callback_hint": "अपना नंबर छोड़ें — मालिक को तुरंत सूचना मिलेगी और वे आपको कॉल करेंगे। उनका नंबर निजी रहेगा।",
        "your_phone": "आपका फ़ोन नंबर",
        "callback_send": "मालिक को सूचित करें",
        "privacy_note": "गोपनीयता-सुरक्षित: मालिक का फ़ोन नंबर कभी नहीं दिखाया जाता।",
        "wa_prefill": "नमस्ते! मैंने आपका Info-Tag स्कैन किया",
        "reward_offered": "लौटाने पर इनाम",
        "sp_heading": "कृपया मेरी मदद करें",
        "sp_body": "हो सकता है मैं बोल न पाऊँ या सवालों के जवाब न दे पाऊँ। कृपया मेरे साथ धैर्य और दया से पेश आएँ।",
        "sp_guardian": "मेरे अभिभावक",
        "sp_call_guardian": "मेरे अभिभावक को कॉल करें",
        "sp_notes": "मेरे बारे में ज़रूरी बातें",
        "sp_home": "मैं यहाँ के पास रहता/रहती हूँ",
        "sp_thanks": "रुककर मदद करने के लिए धन्यवाद। यह बहुत मायने रखता है।",
    },
}


def t(lang: str, key: str) -> str:
    return STRINGS.get(lang, STRINGS["en"]).get(key) or STRINGS["en"].get(key, key)


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


# ---------------------------------------------------------------------------
# CSS — minimal, single inline block.  Targets ~3KB before gzip.
# ---------------------------------------------------------------------------
CSS = """
*,*::before,*::after{box-sizing:border-box}
html{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;-webkit-text-size-adjust:100%}
body{margin:0;background:#fafafa;color:#0a0a0a}
a{color:inherit}
.brand{font-weight:900;letter-spacing:-0.02em;font-size:18px}
.brand .it{color:#E25822}
.wrap{max-width:480px;margin:0 auto;padding:16px}
header{border-bottom:1px solid #e5e5e5;background:#fff}
header .row{display:flex;align-items:center;justify-content:space-between;height:52px}
.card{background:#fff;border:1px solid #e5e5e5;border-radius:12px;padding:20px;margin:16px 0}
.kicker{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#666}
h1{font-size:24px;margin:6px 0 0;line-height:1.2;letter-spacing:-0.02em}
h2{font-size:14px;letter-spacing:.1em;text-transform:uppercase;color:#666;margin:18px 0 8px;font-weight:600}
.note{background:#f5f5f5;border-radius:8px;padding:12px;margin-top:14px;font-size:15px;white-space:pre-wrap}
.btn{display:flex;align-items:center;justify-content:space-between;width:100%;padding:14px 18px;border:1px solid #e5e5e5;border-radius:18px;background:#fff;color:inherit;text-decoration:none;font:inherit;font-weight:500;margin:0 0 8px;cursor:pointer;text-align:left}
.btn:active{background:#f5f5f5}
.btn .arrow{color:#999;font-size:13px}
.btn-primary{background:#0F172A;color:#fff;border-color:#0F172A;border-radius:9999px;justify-content:center;font-size:15px;padding:14px;font-weight:600}
.btn-primary:active{background:#1f293c}
input,textarea{font:inherit;width:100%;padding:11px 12px;border:1px solid #e5e5e5;border-radius:8px;background:#fff;color:inherit;margin-bottom:10px}
textarea{min-height:96px;resize:vertical}
label.row{display:flex;align-items:center;gap:8px;font-size:14px;color:#444;margin:6px 0 12px}
.lost{background:#fef2f2;border:1px solid #fecaca;color:#dc2626;padding:12px;border-radius:8px;margin-top:14px;font-weight:600;font-size:14px}
footer{margin-top:24px;padding:16px;text-align:center;font-size:12px;color:#666;border-top:1px solid #e5e5e5}
.honeypot{position:absolute;left:-9999px;top:-9999px}
.thanks{text-align:center;padding:24px 16px;color:#15803d}
.thanks svg{width:48px;height:48px;color:#22c55e}
.muted{color:#666;font-size:13px}
.lang{font-size:13px;color:#666;text-decoration:none;border:1px solid #e5e5e5;padding:6px 10px;border-radius:9999px}
.icon-tag{color:#E25822;vertical-align:-3px;margin-right:4px}

/* Emergency mode */
body.em{background:#fef2f2}
.em-pill{display:inline-flex;align-items:center;gap:6px;background:#dc2626;color:#fff;font-weight:900;font-size:11px;letter-spacing:.15em;text-transform:uppercase;padding:6px 12px;border-radius:9999px}
.em-card{border-color:#fecaca}
.em-blood{font-size:34px;font-weight:900;color:#dc2626;letter-spacing:-0.02em}
.em-field{margin-bottom:12px}
.em-call{display:flex;align-items:center;justify-content:center;gap:10px;background:#dc2626;color:#fff;border:none;font-size:18px;font-weight:900;letter-spacing:.05em;text-transform:uppercase;padding:18px;border-radius:18px;text-decoration:none;position:sticky;bottom:12px;box-shadow:0 8px 24px rgba(220,38,38,.25);margin-top:16px}
.em-call:active{background:#b91c1c}

/* Special-ability (guardian) card */
.sp-pill{display:inline-flex;align-items:center;gap:6px;background:#0369a1;color:#fff;font-weight:900;font-size:11px;letter-spacing:.15em;text-transform:uppercase;padding:6px 12px;border-radius:9999px}
.sp-card{border:1px solid #bae6fd;background:#f0f9ff;border-radius:12px;padding:20px;margin:16px 0}
.sp-call{display:flex;align-items:center;justify-content:center;gap:10px;background:#0369a1;color:#fff;border:none;font-size:17px;font-weight:900;letter-spacing:.03em;padding:16px;border-radius:18px;text-decoration:none;margin-top:14px;box-shadow:0 8px 24px rgba(3,105,161,.25)}
.sp-call:active{background:#075985}
@media (prefers-color-scheme: dark){.sp-card{background:#082f49;border-color:#075985;color:#e0f2fe}}

/* Contact-the-owner buttons */
.btn-contact{display:flex;align-items:center;gap:10px;justify-content:center;width:100%;padding:14px 18px;border-radius:18px;text-decoration:none;font-weight:700;font-size:15px;margin:0 0 8px;border:none;cursor:pointer;font-family:inherit}
.btn-call{background:#16a34a;color:#fff}
.btn-call:active{background:#15803d}
.btn-wa{background:#25D366;color:#fff}
.btn-wa:active{background:#1ebe5b}
.btn-sms{background:#0ea5e9;color:#fff}
.btn-sms:active{background:#0284c7}
.privacy-note{display:flex;align-items:center;gap:8px;font-size:12px;color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:8px 10px;margin-top:6px}
.reward{display:flex;align-items:center;gap:10px;background:#fffbeb;border:1px solid #fcd34d;color:#92400e;border-radius:10px;padding:12px 14px;margin-top:14px;font-weight:700;font-size:15px}
@media (prefers-color-scheme: dark){.reward{background:#3b2f0b;border-color:#a16207;color:#fcd34d}}
@media (prefers-color-scheme: dark){.privacy-note{background:#052e16;border-color:#14532d;color:#86efac}}

/* Hide elements when JS enables them */
.no-js-only{display:block}
.js-only{display:none}
.js .no-js-only{display:none}
.js .js-only{display:block}

@media (prefers-color-scheme: dark) {
    body:not(.em){background:#09090b;color:#fafafa}
    .card,header,input,textarea,.btn{background:#18181b;border-color:#27272a;color:#fafafa}
    header{border-bottom-color:#27272a}
    .note{background:#27272a}
    .btn-primary{background:#fafafa;color:#0F172A;border-color:#fafafa}
    .muted,.kicker,h2,footer{color:#a3a3a3}
    .lang{border-color:#27272a;color:#a3a3a3}
}
"""


def render_layout(*, lang: str, body: str, emergency: bool = False, title: str = "Info-Tag") -> str:
    other_lang = "hi" if lang == "en" else "en"
    body_class = "em" if emergency else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="{'#dc2626' if emergency else '#0F172A'}">
<meta name="referrer" content="no-referrer">
<meta name="robots" content="noindex,nofollow">
<title>{esc(title)} — Info-Tag</title>
<meta name="description" content="A kind person scanned this Info-Tag. Help reunite an item with its owner.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230F172A'/%3E%3Cpath d='M21 11l-4-4-9 9v4h4l9-9z' stroke='%23E25822' stroke-width='2.4' fill='none' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>{CSS}</style>
<script>document.documentElement.className='js'</script>
</head>
<body class="{body_class}">
<header><div class="wrap row">
<a class="brand" href="/" data-testid="finder-brand"><span aria-hidden="true" class="icon-tag">⛓︎</span>Info-<span class="it">Tag</span></a>
<a class="lang" href="?lang={other_lang}" data-testid="finder-lang-switch">{esc(STRINGS[lang]['lang_switch'])}</a>
</div></header>
<main class="wrap">{body}</main>
<footer class="wrap">
<div>{esc(STRINGS[lang]['powered_by'])}</div>
<div style="margin-top:6px">🇮🇳 {esc(STRINGS[lang]['made_in_india'])}</div>
</footer>
</body>
</html>"""


def render_not_found(lang: str) -> str:
    body = f"""
<div class="card" data-testid="finder-not-found" style="text-align:center">
<div style="font-size:42px;line-height:1">⚠︎</div>
<h1>{esc(t(lang,'tag_not_found'))}</h1>
<p class="muted">{esc(t(lang,'tag_not_found_help'))}</p>
</div>"""
    return render_layout(lang=lang, body=body, title=t(lang, "tag_not_found"))


def render_unclaimed(lang: str, slug: str) -> str:
    body = f"""
<div class="card" data-testid="finder-unclaimed" style="text-align:center">
<div style="font-size:42px;line-height:1">⚐</div>
<h1>{esc(t(lang,'unclaimed_title'))}</h1>
<p class="muted">{esc(t(lang,'unclaimed_body'))}</p>
<a class="btn-primary" href="/claim/{esc(slug)}" data-testid="finder-claim-btn" style="display:inline-block;margin-top:10px;padding:14px 22px;text-decoration:none">Claim this tag</a>
</div>"""
    return render_layout(lang=lang, body=body, title=t(lang, "unclaimed_title"))


def render_thanks(lang: str, slug: str) -> str:
    body = f"""
<div class="card" data-testid="finder-thanks">
<div class="thanks">
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
<h1 style="color:inherit">{esc(t(lang,'sent_thanks'))}</h1>
</div>
<a class="btn" href="/api/finder/{esc(slug)}?lang={esc(lang)}" data-testid="finder-back-btn">{esc(t(lang,'back'))}<span class="arrow">→</span></a>
</div>"""
    return render_layout(lang=lang, body=body, title="Thanks")


# Action types each tag type exposes as one-tap buttons
QUICK_ACTIONS = {
    "vehicle": ["wrong_parking", "headlight_on", "found"],
    "pet": ["found"],
    "luggage": ["found"],
    "keys": ["found"],
    "general": ["found"],
    "medical": [],
    "special": ["found"],
}

ACTION_LABEL_KEY = {
    "wrong_parking": "wrong_parking",
    "headlight_on": "headlight_on",
    "found": "found_share",
}


def _quick_action_form(slug: str, action: str, label: str, lang: str) -> str:
    return f"""
<form method="post" action="/api/finder/{esc(slug)}/action" class="js-quick" data-testid="finder-action-form-{esc(action)}">
<input type="hidden" name="action_type" value="{esc(action)}">
<input type="hidden" name="lang" value="{esc(lang)}">
<input type="hidden" name="body" value="{esc(label)}">
<input type="hidden" name="location" value="" data-loc-target>
<input type="text" name="bot_check" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
<button class="btn" type="submit" data-testid="finder-action-{esc(action)}">
<span>{esc(label)}</span><span class="arrow">→</span>
</button>
</form>"""


def _contact_section(lang: str, slug: str, contact: Optional[dict], display_name: str) -> str:
    """Contact-the-owner block — the mask / no-mask feature.

    direct → free tel: / wa.me / sms: deep links with the owner's number.
    masked → callback-request form; the owner's number is never in the HTML.
    """
    if not contact:
        return ""
    from urllib.parse import quote

    heading = f'<h2>{esc(t(lang, "contact_owner"))}</h2>'

    if contact.get("mode") == "direct" and contact.get("phone"):
        phone = re.sub(r"[^+\d]", "", contact["phone"])
        wa_digits = phone.lstrip("+")
        wa_text = quote(f"{t(lang, 'wa_prefill')} — {display_name or slug}")
        buttons = []
        if contact.get("call", True):
            buttons.append(
                f'<a class="btn-contact btn-call" href="tel:{esc(phone)}" data-testid="finder-call-owner">📞 {esc(t(lang,"call_owner"))}</a>'
            )
        if contact.get("whatsapp", True):
            buttons.append(
                f'<a class="btn-contact btn-wa" href="https://wa.me/{esc(wa_digits)}?text={wa_text}" rel="noopener" data-testid="finder-whatsapp-owner">💬 {esc(t(lang,"whatsapp_owner"))}</a>'
            )
        if contact.get("sms", True):
            buttons.append(
                f'<a class="btn-contact btn-sms" href="sms:{esc(phone)}" data-testid="finder-sms-owner">✉️ {esc(t(lang,"sms_owner"))}</a>'
            )
        if not buttons:
            return ""
        return heading + "".join(buttons)

    if not contact.get("callback", True):
        return ""
    # Masked mode — free relay: finder leaves their number, owner calls back.
    return f"""{heading}
<div class="card" data-testid="finder-callback-card">
<div style="font-weight:700;margin-bottom:4px">{esc(t(lang,'request_callback'))}</div>
<p class="muted" style="margin:0 0 10px">{esc(t(lang,'callback_hint'))}</p>
<form method="post" action="/api/finder/{esc(slug)}/action" data-testid="finder-callback-form">
<input type="hidden" name="action_type" value="call_request">
<input type="hidden" name="lang" value="{esc(lang)}">
<input type="hidden" name="body" value="Callback requested — please call this finder back.">
<input type="tel" name="finder_contact" placeholder="{esc(t(lang,'your_phone'))}" required minlength="8" autocomplete="tel" data-testid="finder-callback-phone">
<input type="text" name="finder_name" placeholder="{esc(t(lang,'your_name'))}" autocomplete="name" data-testid="finder-callback-name">
<input type="hidden" name="location" value="" data-loc-target>
<input type="text" name="bot_check" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
<button class="btn-contact btn-call" type="submit" data-testid="finder-callback-send">📞 {esc(t(lang,'callback_send'))}</button>
</form>
<div class="privacy-note">🔒 {esc(t(lang,'privacy_note'))}</div>
</div>"""


def _special_section(lang: str, doc: dict) -> str:
    """Guardian card for special-ability tags — children, elders, and people
    who may not be able to speak.  Big, calm, one-tap call button."""
    if doc.get("type") != "special":
        return ""
    public_fields = doc.get("public_fields", {})
    data = doc.get("data", {}) or {}

    def pub(key: str) -> str:
        return str(data.get(key, "") or "") if public_fields.get(key, True) else ""

    guardian_name = pub("guardian_name")
    guardian_phone = re.sub(r"[^+\d]", "", pub("guardian_phone"))
    notes = pub("special_notes")
    home = pub("home_area")

    rows = ""
    if notes:
        rows += f'<div style="margin-top:12px"><div class="kicker">{esc(t(lang,"sp_notes"))}</div><div style="font-weight:600;font-size:16px;white-space:pre-wrap">{esc(notes)}</div></div>'
    if home:
        rows += f'<div style="margin-top:12px"><div class="kicker">{esc(t(lang,"sp_home"))}</div><div style="font-weight:600;font-size:16px">{esc(home)}</div></div>'
    if guardian_name:
        rows += f'<div style="margin-top:12px"><div class="kicker">{esc(t(lang,"sp_guardian"))}</div><div style="font-weight:600;font-size:16px">{esc(guardian_name)}</div></div>'
    call_btn = (
        f'<a class="sp-call" href="tel:{esc(guardian_phone)}" data-testid="special-call-guardian">📞 {esc(t(lang,"sp_call_guardian"))}</a>'
        if guardian_phone
        else ""
    )
    return f"""
<div class="sp-card" data-testid="finder-special">
<span class="sp-pill">🤝 {esc(t(lang,'sp_heading'))}</span>
<p style="margin:12px 0 0;font-size:16px;font-weight:600">{esc(t(lang,'sp_body'))}</p>
{rows}
{call_btn}
<p class="muted" style="margin:12px 0 0">{esc(t(lang,'sp_thanks'))}</p>
</div>"""


def render_claimed(lang: str, doc: dict, contact: Optional[dict] = None) -> str:
    actions = QUICK_ACTIONS.get(doc.get("type", "general"), [])
    public_fields = doc.get("public_fields", {})
    display_name = doc.get("display_name", "") if public_fields.get("display_name", True) else ""
    message = doc.get("message", "") if public_fields.get("message", True) else ""

    lost_banner = (
        f'<div class="lost" data-testid="finder-lost-banner">{esc(t(lang, "reported_lost"))}</div>'
        if doc.get("status") == "lost"
        else ""
    )
    reward = (doc.get("data") or {}).get("reward", "")
    reward_banner = (
        f'<div class="reward" data-testid="finder-reward">🎁 {esc(t(lang, "reward_offered"))}: {esc(str(reward))}</div>'
        if reward and public_fields.get("reward", True)
        else ""
    )
    note_html = (
        f"""
        <div style="margin-top:14px">
          <div class="kicker">{esc(t(lang,'owner_says'))}</div>
          <div class="note" data-testid="finder-message">{esc(message)}</div>
        </div>"""
        if message
        else ""
    )

    actions_html = ""
    if actions:
        action_label_map = {
            "wrong_parking": t(lang, "wrong_parking"),
            "headlight_on": t(lang, "headlight_on"),
            "found": t(lang, "found_share"),
        }
        actions_html = f'<h2>{esc(t(lang, "quick_actions"))}</h2>' + "".join(
            _quick_action_form(doc["slug"], a, action_label_map[a], lang) for a in actions
        )

    body = f"""
<div class="card" data-testid="finder-claimed">
<div class="kicker">{esc(doc.get('type','item').upper())}</div>
<h1 data-testid="finder-display-name">{esc(display_name) or 'Info-Tag'}</h1>
<div class="muted" style="margin-top:4px">{esc(t(lang,'header'))}</div>
{lost_banner}
{reward_banner}
{note_html}
</div>
{_special_section(lang, doc)}
{_contact_section(lang, doc["slug"], contact, display_name)}
{actions_html}
<div class="card">
<h2>{esc(t(lang,'send_message'))}</h2>
<form method="post" action="/api/finder/{esc(doc['slug'])}/action" data-testid="finder-message-form">
<input type="hidden" name="action_type" value="message">
<input type="hidden" name="lang" value="{esc(lang)}">
<input type="text" name="finder_name" placeholder="{esc(t(lang,'your_name'))}" autocomplete="name" data-testid="finder-name-input">
<input type="text" name="finder_contact" placeholder="{esc(t(lang,'your_contact'))}" autocomplete="email" data-testid="finder-contact-input">
<textarea name="body" placeholder="{esc(t(lang,'message_ph'))}" required data-testid="finder-body-input"></textarea>
<label class="row js-only"><input type="checkbox" name="share_location" value="1" checked data-testid="finder-share-loc">{esc(t(lang,'include_loc'))}</label>
<input type="hidden" name="location" value="" data-loc-target>
<input type="text" name="bot_check" class="honeypot" tabindex="-1" autocomplete="off" aria-hidden="true">
<button class="btn-primary" type="submit" data-testid="finder-send-btn">{esc(t(lang,'send'))}</button>
</form>
</div>
<script>/* progressive-enhancement: capture geolocation for finder forms */
(function(){{if(!navigator.geolocation)return;
navigator.geolocation.getCurrentPosition(function(p){{
var v=p.coords.latitude+','+p.coords.longitude;
document.querySelectorAll('[data-loc-target]').forEach(function(el){{el.value=v}});
}},function(){{}},{{timeout:5000,enableHighAccuracy:false}});}})();</script>"""
    return render_layout(lang=lang, body=body, title=display_name or "Info-Tag")


def render_emergency(lang: str, doc: dict, em: dict) -> str:
    phone = re.sub(r"[^+\d]", "", em.get("emergency_contact_phone", "") or "")
    last = em.get("last_updated", "")
    last_str = ""
    if last:
        try:
            last_str = datetime.fromisoformat(last).strftime("%d %b %Y")
        except (ValueError, TypeError):
            last_str = last[:10]

    def field(label: str, value: str, highlight: bool = False) -> str:
        if not value:
            return ""
        cls = "em-blood" if highlight else ""
        return f"""<div class="em-field">
<div class="kicker">{esc(label)}</div>
<div class="{cls}" style="font-weight:600;font-size:{'34px' if highlight else '17px'}">{esc(value)}</div>
</div>"""

    name = doc.get("display_name", "")
    call_btn = ""
    if phone:
        call_btn = f"""<a class="em-call" href="tel:{esc(phone)}" data-testid="emergency-call-btn">
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
{esc(t(lang,'em_call'))}
</a>"""
    contact_name = em.get("emergency_contact_name", "")
    contact_line = f'<p class="muted" style="text-align:center;margin:6px 0 0" data-testid="emergency-contact-name">{esc(contact_name)}</p>' if contact_name else ""

    body = f"""
<div style="text-align:center;margin:18px 0 12px">
<span class="em-pill" data-testid="emergency-pill">
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
{esc(t(lang,'em_heading'))}
</span>
<h1 style="margin-top:14px" data-testid="emergency-name">{esc(name)}</h1>
</div>
<div class="card em-card" data-testid="emergency-root">
{field(t(lang,'em_blood'), em.get('blood_group',''), highlight=True)}
{field(t(lang,'em_allergies'), em.get('allergies',''))}
{field(t(lang,'em_chronic'), em.get('chronic_conditions',''))}
{field(t(lang,'em_ps'), em.get('nearest_police_station',''))}
{field('Notes', em.get('additional_notes',''))}
<p class="muted" style="border-top:1px solid #fecaca;padding-top:10px;margin-top:14px">
{esc(t(lang,'verify_notice'))}
{(' · ' + esc(t(lang,'last_updated')) + ': ' + esc(last_str)) if last_str else ''}
</p>
</div>
{call_btn}
{contact_line}
<p class="muted" style="text-align:center;margin-top:10px">{esc(t(lang,'em_disclaimer'))}</p>"""
    return render_layout(lang=lang, body=body, emergency=True, title=name or "Medical ID")


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(text: str) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()[:2000]


def _resolve_lang(request: Request, override: Optional[str] = None) -> str:
    if override and override in STRINGS:
        return override
    qp = request.query_params.get("lang")
    if qp and qp in STRINGS:
        return qp
    accept = (request.headers.get("accept-language") or "").lower()
    if accept.startswith("hi"):
        return "hi"
    return "en"


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------
@router.get("/{slug}", response_class=HTMLResponse)
async def finder_page(slug: str, request: Request) -> HTMLResponse:
    db = get_db()
    lang = _resolve_lang(request)
    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        return HTMLResponse(render_not_found(lang), status_code=404)

    # Record the scan (dedupe within 30s per hashed-IP)
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "0.0.0.0")
    ip_h = hash_ip(ip)
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=30)).isoformat()
    recent = await db.scans.find_one(
        {"tag_id": doc["id"], "ip_hash": ip_h, "scanned_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1},
    )
    if recent is None:
        await db.scans.insert_one(
            {
                "id": f"scan_{uuid.uuid4().hex[:12]}",
                "tag_id": doc["id"],
                "scanned_at": now.isoformat(),
                "approx_location": None,
                "ip_hash": ip_h,
                "user_agent": (request.headers.get("user-agent") or "")[:200],
            }
        )
        # Free Web Push scan alert (opt-in via notify_on_scan)
        if doc.get("owner_id"):
            owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
            if owner and owner.get("notify_on_scan"):
                name = doc.get("display_name") or doc.get("label") or "your tag"
                await push_owner(db, owner["id"], "Info-Tag · tag scanned 👀", f"Someone just scanned “{name}”.", "/dashboard")

    if doc.get("owner_id") is None:
        return HTMLResponse(render_unclaimed(lang, slug))

    if doc.get("type") == "medical":
        profile = await db.profiles.find_one({"tag_id": doc["id"]}, {"_id": 0})
        if profile and profile.get("emergency_mode") and profile.get("consent_given"):
            return HTMLResponse(render_emergency(lang, doc, profile))

    from routes.tag_routes import build_contact_block

    contact = await build_contact_block(db, doc)
    return HTMLResponse(render_claimed(lang, doc, contact))


@router.post("/{slug}/action", response_class=HTMLResponse)
async def finder_action(
    slug: str,
    request: Request,
    action_type: str = Form(...),
    lang: str = Form("en"),
    body: str = Form(""),
    finder_name: str = Form(""),
    finder_contact: str = Form(""),
    location: str = Form(""),
    share_location: str = Form(""),
    bot_check: str = Form(""),
) -> HTMLResponse:
    if action_type not in {"message", "wrong_parking", "headlight_on", "found", "call_request"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    db = get_db()
    lang = lang if lang in STRINGS else "en"

    # Honeypot — silently succeed so bots can't differentiate
    if bot_check:
        return HTMLResponse(render_thanks(lang, slug))

    doc = await db.tags.find_one({"slug": slug}, {"_id": 0})
    if not doc:
        return HTMLResponse(render_not_found(lang), status_code=404)
    if not doc.get("owner_id"):
        return HTMLResponse(render_unclaimed(lang, slug), status_code=400)

    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "0.0.0.0")
    ip_h = hash_ip(ip)

    # Minimal rate limit — 30s per (tag, ip, action)
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    recent = await db.messages.find_one(
        {"tag_id": doc["id"], "ip_hash": ip_h, "action_type": action_type, "created_at": {"$gte": cutoff}}
    )
    if recent:
        return HTMLResponse(render_thanks(lang, slug))

    loc = None
    if location and "," in location and (share_location or action_type != "message"):
        try:
            lat_s, lng_s = location.split(",", 1)
            loc = {"lat": float(lat_s), "lng": float(lng_s)}
        except (ValueError, TypeError):
            loc = None

    msg = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "tag_id": doc["id"],
        "action_type": action_type,
        "finder_name": _sanitize(finder_name),
        "finder_contact": _sanitize(finder_contact),
        "body": _sanitize(body),
        "location": loc,
        "ip_hash": ip_h,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(msg)

    owner = await db.users.find_one({"id": doc["owner_id"]}, {"_id": 0})
    if owner and owner.get("notify_on_message", True):
        text = (
            f"Action: {action_type}\n"
            f"Tag: {doc.get('display_name') or doc.get('label')}\n"
            f"Message: {msg['body']}\n"
            f"From: {msg['finder_name'] or 'anonymous'} {msg['finder_contact']}\n"
        )
        if loc:
            text += f"Location: https://maps.google.com/?q={loc['lat']},{loc['lng']}\n"
        notify_owner(owner, f"[Info-Tag] {action_type.replace('_', ' ')} on your tag", text)
        await push_owner(
            db, owner["id"],
            f"Info-Tag · {action_type.replace('_', ' ')} 📨",
            (msg["body"] or "A finder reached out about your tag.")[:140],
        )

    return HTMLResponse(render_thanks(lang, slug))
