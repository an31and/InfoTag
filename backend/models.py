"""Pydantic models for Info-Tag.

We keep MongoDB documents flat and JSON-serialisable.  All ObjectIds are
avoided in favour of UUID strings stored in the document body so the API
never has to translate between BSON and JSON.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TagType = Literal["vehicle", "pet", "luggage", "keys", "medical", "special", "general"]
TagStatus = Literal["active", "lost", "found"]
ActionType = Literal[
    "message",
    "wrong_parking",
    "headlight_on",
    "found",
    "call_request",
]


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: EmailStr
    display_name: str = ""
    phone: str = ""  # E.164-ish; used for alerts + optional direct-contact tags
    notify_on_message: bool = True
    notify_on_scan: bool = False
    whatsapp_alerts: bool = False  # fan-out finder alerts to WhatsApp (env-gated)
    sms_alerts: bool = False  # fan-out finder alerts to SMS (env-gated)
    locale: str = "en"
    auth_provider: str = "password"  # password | google | both
    role: str = "user"  # user | admin
    created_at: str


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = ""


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class UpdateUserPayload(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    notify_on_message: Optional[bool] = None
    notify_on_scan: Optional[bool] = None
    whatsapp_alerts: Optional[bool] = None
    sms_alerts: Optional[bool] = None
    locale: Optional[str] = None


class ChangePasswordPayload(BaseModel):
    current_password: Optional[str] = None
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------
DEFAULT_PUBLIC_FIELDS: dict[str, bool] = {
    "display_name": True,
    "message": True,
    "type": True,
    # vehicle / pet specific
    "vehicle_make_model": True,
    "vehicle_plate": False,
    "pet_name": True,
    "pet_breed": True,
    # generic notes
    "note": True,
    # optional thank-you reward shown to finders
    "reward": True,
    # special-ability (guardian) tags — for children, elders and people who
    # may not be able to speak; the guardian phone is public on purpose
    "guardian_name": True,
    "guardian_phone": True,
    "special_notes": True,
    "home_area": True,
}

# Per-tag contact preference — the "mask / no-mask" switch.
#   masked  → the owner's number is NEVER shown; finders reach the owner via
#             the server relay (message / callback request / Twilio bridge).
#   direct  → the finder page shows one-tap Call / WhatsApp / SMS deep links
#             using the owner's phone (free — no telephony provider needed).
ContactMode = Literal["masked", "direct"]

DEFAULT_CONTACT: dict[str, Any] = {
    "mode": "masked",
    "show_call": True,       # direct mode: tel: link · masked mode: callback request
    "show_whatsapp": True,   # direct mode: wa.me link
    "show_sms": True,        # direct mode: sms: link
}


class TagContact(BaseModel):
    mode: ContactMode = "masked"
    show_call: bool = True
    show_whatsapp: bool = True
    show_sms: bool = True


class TagCreatePayload(BaseModel):
    type: TagType
    label: str = ""
    display_name: str = ""
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    public_fields: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_PUBLIC_FIELDS))
    contact: TagContact = Field(default_factory=TagContact)


class TagUpdatePayload(BaseModel):
    label: Optional[str] = None
    display_name: Optional[str] = None
    message: Optional[str] = None
    status: Optional[TagStatus] = None
    data: Optional[dict[str, Any]] = None
    public_fields: Optional[dict[str, bool]] = None
    contact: Optional[TagContact] = None


class TagOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    slug: str
    owner_id: Optional[str]
    type: TagType
    label: str
    display_name: str
    message: str
    status: TagStatus
    data: dict[str, Any]
    public_fields: dict[str, bool]
    contact: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_CONTACT))
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Profile (medical / emergency)
# ---------------------------------------------------------------------------
class ProfilePayload(BaseModel):
    emergency_mode: bool = False
    blood_group: str = ""
    allergies: str = ""
    chronic_conditions: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    nearest_police_station: str = ""
    additional_notes: str = ""
    consent_given: bool = False


class ProfileOut(ProfilePayload):
    id: str
    tag_id: str
    last_updated: str


# ---------------------------------------------------------------------------
# Messages from finders
# ---------------------------------------------------------------------------
class MessageCreatePayload(BaseModel):
    action_type: ActionType
    finder_name: str = ""
    finder_contact: str = ""
    finder_phone: str = ""  # used by call_request so the owner can call back
    body: str = ""
    location: Optional[dict[str, float]] = None  # {lat, lng}
    bot_check: str = ""  # honeypot; should remain empty


class MessageOut(BaseModel):
    id: str
    tag_id: str
    action_type: ActionType
    finder_name: str
    finder_contact: str
    body: str
    location: Optional[dict[str, float]]
    created_at: str


# ---------------------------------------------------------------------------
# Feedback / comments (public submission, admin-moderated visibility)
# ---------------------------------------------------------------------------
class FeedbackCreatePayload(BaseModel):
    name: str = ""
    email: str = ""
    message: str = Field(min_length=1, max_length=2000)
    rating: int = Field(default=5, ge=1, le=5)
    bot_check: str = ""  # honeypot; should remain empty


# ---------------------------------------------------------------------------
# Public finder view (carefully curated, never returns owner contact)
# ---------------------------------------------------------------------------
class FinderView(BaseModel):
    slug: str
    type: TagType
    status: TagStatus
    display_name: str
    message: str
    public_data: dict[str, Any]
    is_unclaimed: bool
    # Contact block — what the finder may use to reach the owner.
    #   {"mode": "direct", "phone": "+91…", "call": true, "whatsapp": true, "sms": true}
    #   {"mode": "masked", "callback": true, "masked_call": <twilio-configured>}
    contact: Optional[dict[str, Any]] = None
    # Medical-only fields (only populated when emergency_mode + consent_given)
    emergency: Optional[dict[str, Any]] = None
