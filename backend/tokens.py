"""Signed, permanent event-tag tokens.

Why signed tokens
-----------------
Event Mode prints tags in bulk (hundreds today, millions over time).  Storing
one MongoDB row per *unclaimed* tag would exhaust the free Atlas M0 tier
(~512 MB) long before a million tags.  Instead every printed tag carries a
token that is *derived* from ``(batch_id, serial)`` and an HMAC secret:

    body  = version(1 byte) | bid(3 bytes) | serial(3 bytes)
    token = base32(body | HMAC-SHA256(key, body)[:10])      # 28 chars, 80-bit sig

* Unclaimed tags need **no database row** — the server verifies the HMAC.
* A row is created only when somebody claims the tag.
* Tokens never expire: a tag printed today keeps working for as long as the
  signing key exists.  Keys are therefore never rotated *out*; new keys may be
  added for new batches (each batch records the key id it was signed with).

The QR payload is ``<BASE>/T/<TOKEN>`` in upper case, which lets the QR use
the compact alphanumeric mode (≈ version 4 at error-correction H for a short
domain) — bigger modules, better scans on a 2 cm sticker.

Short codes
-----------
Printed under the QR for people without a camera: ``PK24-0137-7QX2`` =
event code, event-wide serial, and a 4-char Crockford check (20 bits of a
second HMAC) so codes cannot be enumerated by simply counting.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_VERSION = 1
SIG_BYTES = 10  # 80-bit signature
BODY_BYTES = 7
TOKEN_LEN = 28  # base32 of 17 bytes, padding stripped
MAX_BID = (1 << 24) - 1
MAX_SERIAL = (1 << 24) - 1

_B32_RE = re.compile(r"^[A-Z2-7]{28}$")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_RE = re.compile(r"^([A-Z0-9]{2,8})-(\d{1,8})-([0-9A-Z]{4})$")


# ---------------------------------------------------------------------------
# Key ring
# ---------------------------------------------------------------------------
class KeyRing:
    """Signing keys by id.  ``active`` signs new batches; all keys verify."""

    def __init__(self, keys: dict[str, bytes], active: str):
        if active not in keys:
            raise ValueError("active key id missing from key ring")
        self.keys = keys
        self.active = active

    def get(self, kid: str) -> Optional[bytes]:
        return self.keys.get(kid)


def _normalise_secret(raw: str) -> bytes:
    # Any sufficiently long string works; hashing gives a uniform 32-byte key.
    return hashlib.sha256(raw.encode("utf-8")).digest()


def parse_env_keys(raw: str) -> dict[str, bytes]:
    """``TAG_SIGNING_KEYS="k1:<secret>,k2:<secret>"`` → {kid: key}."""
    keys: dict[str, bytes] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        kid, secret = part.split(":", 1)
        kid, secret = kid.strip(), secret.strip()
        if len(secret) < 32:
            raise ValueError(f"TAG_SIGNING_KEYS entry {kid!r} must be at least 32 characters")
        keys[kid] = _normalise_secret(secret)
    return keys


_keyring: Optional[KeyRing] = None


async def load_keyring(db, force: bool = False) -> KeyRing:
    """Env keys win; otherwise a random key is created once and kept in Mongo.

    The auto-generated key makes a zero-config deploy safe (tags stay valid
    across restarts because the key lives in the database), but production
    should set ``TAG_SIGNING_KEYS`` and back it up — losing every key means
    every unclaimed printed tag stops working.
    """
    global _keyring
    if _keyring is not None and not force:
        return _keyring
    keys: dict[str, bytes] = {}
    doc = await db.settings.find_one({"id": "tag_signing_keys"}, {"_id": 0}) or {}
    for kid, hexkey in (doc.get("keys") or {}).items():
        keys[kid] = bytes.fromhex(hexkey)
    env_keys = parse_env_keys(os.environ.get("TAG_SIGNING_KEYS", ""))
    keys.update(env_keys)
    if env_keys:
        active = list(env_keys)[-1]
    elif "db0" in keys:
        active = "db0"
    else:
        new = secrets.token_bytes(32)
        await db.settings.update_one(
            {"id": "tag_signing_keys"},
            {"$set": {"keys.db0": new.hex()}},
            upsert=True,
        )
        keys["db0"] = new
        active = "db0"
        logger.warning(
            "Event Mode: generated a tag signing key and stored it in MongoDB. "
            "Back up the database (or set TAG_SIGNING_KEYS) — printed tags depend on it."
        )
    _keyring = KeyRing(keys, active)
    return _keyring


def reset_keyring_cache() -> None:
    global _keyring
    _keyring = None


# ---------------------------------------------------------------------------
# Token encode / decode
# ---------------------------------------------------------------------------
def _body(bid: int, serial: int) -> bytes:
    if not (0 <= bid <= MAX_BID and 0 <= serial <= MAX_SERIAL):
        raise ValueError("bid/serial out of range")
    return bytes([TOKEN_VERSION]) + bid.to_bytes(3, "big") + serial.to_bytes(3, "big")


def _sig(key: bytes, body: bytes) -> bytes:
    return hmac.digest(key, body, "sha256")[:SIG_BYTES]


def encode_token(key: bytes, bid: int, serial: int) -> str:
    body = _body(bid, serial)
    return base64.b32encode(body + _sig(key, body)).decode("ascii").rstrip("=")


def parse_token(token: str) -> Optional[tuple[int, int, bytes, bytes]]:
    """Structural parse only (no key needed) → (bid, serial, body, sig)."""
    tok = (token or "").strip().upper()
    if not _B32_RE.match(tok):
        return None
    try:
        raw = base64.b32decode(tok + "====")
    except (ValueError, TypeError):
        return None
    if len(raw) != BODY_BYTES + SIG_BYTES or raw[0] != TOKEN_VERSION:
        return None
    # The last base32 char carries 4 padding bits; reject non-canonical
    # spellings so each tag has exactly one valid token string.
    if base64.b32encode(raw).decode("ascii").rstrip("=") != tok:
        return None
    body, sig = raw[:BODY_BYTES], raw[BODY_BYTES:]
    bid = int.from_bytes(body[1:4], "big")
    serial = int.from_bytes(body[4:7], "big")
    return bid, serial, body, sig


def verify_sig(key: bytes, body: bytes, sig: bytes) -> bool:
    return hmac.compare_digest(_sig(key, body), sig)


# ---------------------------------------------------------------------------
# Short human-typable codes
# ---------------------------------------------------------------------------
def _check_chars(key: bytes, event_code: str, serial: int) -> str:
    d = hmac.digest(key, f"code|{event_code}|{serial}".encode(), "sha256")
    n = int.from_bytes(d[:3], "big") >> 4  # 20 bits
    out = ""
    for _ in range(4):
        out = _CROCKFORD[n & 31] + out
        n >>= 5
    return out


def short_code(key: bytes, event_code: str, serial: int) -> str:
    return f"{event_code}-{serial:04d}-{_check_chars(key, event_code, serial)}"


def normalise_code(code: str) -> str:
    """Upper-case and map look-alike characters (Crockford rules)."""
    c = re.sub(r"[\s_\u2013\u2014-]+", "-", (code or "").strip().upper())
    return c.strip("-")


def parse_code(code: str) -> Optional[tuple[str, int, str]]:
    """``PK24-0137-7QX2`` → ("PK24", 137, "7QX2").  Structure only."""
    c = normalise_code(code)
    m = _CODE_RE.match(c)
    if not m:
        return None
    check = m.group(3).replace("O", "0").replace("I", "1").replace("L", "1")
    return m.group(1), int(m.group(2)), check


def verify_code(key: bytes, event_code: str, serial: int, check: str) -> bool:
    return hmac.compare_digest(_check_chars(key, event_code, serial), check)


def qr_url(base: str, token: str) -> str:
    """Absolute QR payload.  Scheme+host upper-cased → QR alphanumeric mode."""
    base = (base or "").rstrip("/")
    m = re.match(r"^(https?://[^/]+)(/.*)?$", base, re.I)
    if m and not m.group(2):
        return f"{m.group(1).upper()}/T/{token}"
    return f"{base}/t/{token}"
