"""Email / WhatsApp / Twilio notification helpers.

These are env-gated — if the credentials are missing the helpers silently
log and return.  This lets the app run with zero third-party setup.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def email_enabled() -> bool:
    if os.environ.get("SENDGRID_API_KEY"):
        return True
    if os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"):
        return True
    return False


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort email sender.  Returns True if the email was dispatched."""
    if not to_email:
        return False
    from_email = os.environ.get("EMAIL_FROM") or "no-reply@info-tag.in"

    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    if sendgrid_key:
        try:
            import requests

            requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {sendgrid_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": from_email},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
                timeout=8,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SendGrid send failed: %s", exc)
            return False

    smtp_host = os.environ.get("SMTP_HOST")
    if smtp_host and os.environ.get("SMTP_USER"):
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email
            with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", "587"))) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
                s.sendmail(from_email, [to_email], msg.as_string())
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SMTP send failed: %s", exc)
            return False

    logger.info("Email skipped (no provider configured) to=%s subj=%s", to_email, subject)
    return False


def _clean_phone(phone: str | None) -> str:
    """Keep digits and a leading '+'. Returns '' when unusable."""
    if not phone:
        return ""
    cleaned = re.sub(r"[^+\d]", "", phone)
    digits = cleaned.lstrip("+")
    if len(digits) < 8:
        return ""
    return cleaned


def phone_last_digits(phone: str | None, n: int = 10) -> str:
    """Last N digits of a phone number, ignoring +, spaces, dashes.

    Used to match an inbound WhatsApp wa_id (always plain digits, e.g.
    "919876543210") against however a user happened to type their number
    in Settings (e.g. "+91 98765 43210"). Comparing only the last 10
    digits sidesteps country-code formatting differences without needing
    every stored phone number to be normalised on write.
    """
    digits = re.sub(r"\D", "", phone or "")
    return digits[-n:] if digits else ""


# ---------------------------------------------------------------------------
# WhatsApp — Meta WhatsApp Cloud API (free service-conversation tier)
# Env: WHATSAPP_TOKEN + WHATSAPP_PHONE_NUMBER_ID
# (legacy WHATSAPP_API_KEY is still honoured as an alias for WHATSAPP_TOKEN)
# ---------------------------------------------------------------------------
def whatsapp_enabled() -> bool:
    token = os.environ.get("WHATSAPP_TOKEN") or os.environ.get("WHATSAPP_API_KEY")
    return bool(token and os.environ.get("WHATSAPP_PHONE_NUMBER_ID"))


def whatsapp_business_number() -> str:
    """The dialable business number (E.164), for building wa.me opt-in links.

    This is deliberately separate from WHATSAPP_PHONE_NUMBER_ID — that's an
    opaque Graph API asset id, not a phone number, and isn't reversible to
    one without an extra API call. Set WHATSAPP_BUSINESS_NUMBER once you've
    registered a real number (e.g. "+919999999999").
    """
    return _clean_phone(os.environ.get("WHATSAPP_BUSINESS_NUMBER", ""))


def send_whatsapp(to_phone: str, body: str) -> bool:
    """Send a WhatsApp text via the Meta Cloud API.  Best-effort, env-gated."""
    to_phone = _clean_phone(to_phone)
    if not to_phone or not whatsapp_enabled():
        logger.info("WhatsApp skipped (not configured or no phone) to=%s", to_phone)
        return False
    token = os.environ.get("WHATSAPP_TOKEN") or os.environ.get("WHATSAPP_API_KEY")
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    try:
        import requests

        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "to": to_phone.lstrip("+"),
                "type": "text",
                "text": {"body": body[:4000]},
            },
            timeout=8,
        )
        if resp.status_code >= 300:
            logger.warning("WhatsApp send failed: %s %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("WhatsApp send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# WhatsApp diagnostics — surface Meta's actual response for the admin portal.
# send_whatsapp() deliberately swallows errors (it's fire-and-forget in the
# request path); these helpers instead RETURN what Meta said, so the admin can
# see the real reason a message didn't go out (expired token, 24h window,
# test-mode allowlist, wrong number id, …).
# ---------------------------------------------------------------------------
def _whatsapp_token() -> str:
    return os.environ.get("WHATSAPP_TOKEN") or os.environ.get("WHATSAPP_API_KEY") or ""


def whatsapp_config_status() -> dict:
    """Which WhatsApp env vars are present (booleans only — never leak secrets)."""
    return {
        "token_set": bool(_whatsapp_token()),
        "phone_number_id_set": bool(os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
        "business_number_set": bool(os.environ.get("WHATSAPP_BUSINESS_NUMBER")),
        "verify_token_set": bool(os.environ.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN")),
        "app_secret_set": bool(os.environ.get("META_APP_SECRET")),
        "enabled": whatsapp_enabled(),
    }


def whatsapp_probe() -> dict:
    """Live GET against Graph to validate the token + phone-number id pair.

    A 200 means the token is valid and can see the number. A 190 means the
    token is expired/invalid; a 100/803 usually means a wrong phone-number id.
    No message is sent.
    """
    token, phone_id = _whatsapp_token(), os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_id:
        return {"ok": False, "reason": "Token or phone-number id not configured"}
    try:
        import requests

        resp = requests.get(
            f"https://graph.facebook.com/v19.0/{phone_id}",
            params={"fields": "display_phone_number,verified_name,quality_rating,code_verification_status"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        return {"ok": resp.status_code < 300, "status_code": resp.status_code, "response": _safe_json(resp)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def whatsapp_send_debug(to_phone: str, body: str) -> dict:
    """Send a text and RETURN Meta's status + body (unlike send_whatsapp)."""
    to = _clean_phone(to_phone)
    token, phone_id = _whatsapp_token(), os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not to:
        return {"ok": False, "reason": "Recipient number looks invalid"}
    if not token or not phone_id:
        return {"ok": False, "reason": "Token or phone-number id not configured"}
    try:
        import requests

        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text", "text": {"body": body[:1000]}},
            timeout=8,
        )
        return {"ok": resp.status_code < 300, "status_code": resp.status_code, "response": _safe_json(resp)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"raw": (resp.text or "")[:500]}


# ---------------------------------------------------------------------------
# Twilio — SMS + masked-call bridge (paid, env-gated)
# Env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
# ---------------------------------------------------------------------------
def twilio_enabled() -> bool:
    return bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"))


def sms_enabled() -> bool:
    return twilio_enabled() and bool(os.environ.get("TWILIO_FROM_NUMBER"))


def masked_call_enabled() -> bool:
    return sms_enabled()


def send_sms(to_phone: str, body: str) -> bool:
    """Send an SMS via the Twilio REST API.  Best-effort, env-gated."""
    to_phone = _clean_phone(to_phone)
    if not to_phone or not sms_enabled():
        logger.info("SMS skipped (not configured or no phone) to=%s", to_phone)
        return False
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM_NUMBER"]
    try:
        import requests

        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            auth=(sid, token),
            data={"To": to_phone, "From": from_number, "Body": body[:1500]},
            timeout=8,
        )
        if resp.status_code >= 300:
            logger.warning("Twilio SMS failed: %s %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Twilio SMS failed: %s", exc)
        return False


def start_masked_call(finder_phone: str, owner_phone: str) -> bool:
    """Bridge finder ↔ owner with both numbers hidden behind TWILIO_FROM_NUMBER.

    Twilio first rings the finder; when they pick up, TwiML dials the owner
    with the Twilio number as caller ID — neither party ever sees the other's
    real number.  Best-effort, env-gated.
    """
    finder_phone = _clean_phone(finder_phone)
    owner_phone = _clean_phone(owner_phone)
    if not finder_phone or not owner_phone or not masked_call_enabled():
        logger.info("Masked call skipped (not configured or missing numbers)")
        return False
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM_NUMBER"]
    twiml = (
        "<Response><Say>Connecting you to the Info-Tag owner. "
        "Both numbers stay private.</Say>"
        f'<Dial callerId="{from_number}">{owner_phone}</Dial></Response>'
    )
    try:
        import requests

        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
            auth=(sid, token),
            data={"To": finder_phone, "From": from_number, "Twiml": twiml},
            timeout=8,
        )
        if resp.status_code >= 300:
            logger.warning("Twilio masked call failed: %s %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Twilio masked call failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Owner alert fan-out — one call notifies on every channel the owner enabled
# ---------------------------------------------------------------------------
def notify_owner(owner: dict, subject: str, body: str) -> dict:
    """Send an alert via email + WhatsApp + SMS based on the owner's prefs.

    Each channel is independently best-effort and env-gated, so a missing
    provider never breaks the request path.  Returns per-channel results.
    """
    results = {"email": False, "whatsapp": False, "sms": False}
    if not owner:
        return results
    results["email"] = send_email(owner.get("email", ""), subject, body)
    phone = owner.get("phone", "")
    if phone and owner.get("whatsapp_alerts"):
        results["whatsapp"] = send_whatsapp(phone, f"{subject}\n\n{body}")
    if phone and owner.get("sms_alerts"):
        results["sms"] = send_sms(phone, f"{subject} — {body}"[:1500])
    return results
