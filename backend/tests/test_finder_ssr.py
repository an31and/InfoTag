"""SSR finder page tests — iteration 3.

Verifies the new /api/finder/{slug} server-rendered HTML page.
"""
import gzip
import io
import os
import re
import time
import uuid
import asyncio

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://smart-tags-dev.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "anand@tagit.in"
ADMIN_PASSWORD = "InfoTagAdmin@2026"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def vehicle_tag(admin_session):
    tags = admin_session.get(f"{BASE_URL}/api/tags").json()
    return next(t for t in tags if t["type"] == "vehicle")


@pytest.fixture(scope="module")
def medical_tag(admin_session):
    tags = admin_session.get(f"{BASE_URL}/api/tags").json()
    return next(t for t in tags if t["type"] == "medical")


# ---------- SSR vehicle (claimed) ----------
class TestSSRVehicle:
    def test_vehicle_html_basic(self, vehicle_tag):
        slug = vehicle_tag["slug"]
        r = requests.get(f"{BASE_URL}/api/finder/{slug}")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"content-type={ct}"
        html = r.text
        # brand
        assert "Info-Tag" in html or "Info-<span" in html
        assert 'data-testid="finder-brand"' in html
        # quick action buttons
        assert 'data-testid="finder-action-wrong_parking"' in html
        assert 'data-testid="finder-action-headlight_on"' in html
        # message form
        assert 'data-testid="finder-message-form"' in html
        # no React bundle
        assert "/static/js/main." not in html
        # owner says header copy (English default)
        assert "kind person scanned" in html or "Hi," in html

    def test_vehicle_gzip_under_10kb(self, vehicle_tag):
        slug = vehicle_tag["slug"]
        r = requests.get(f"{BASE_URL}/api/finder/{slug}", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        # If server already returned gzip, requests decompressed it. Re-gzip the text for sizing.
        raw = r.text.encode("utf-8")
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9) as gz:
            gz.write(raw)
        gzipped_size = len(buf.getvalue())
        assert gzipped_size < 10 * 1024, f"gzipped HTML is {gzipped_size} bytes (>10KB)"

    def test_vehicle_hindi(self, vehicle_tag):
        slug = vehicle_tag["slug"]
        r = requests.get(f"{BASE_URL}/api/finder/{slug}?lang=hi")
        assert r.status_code == 200
        html = r.text
        # Devanagari greeting always present
        assert "नमस्ते" in html or "मालिक का संदेश" in html, "Expected Hindi copy missing"


# ---------- SSR medical (emergency view) ----------
class TestSSRMedical:
    def test_medical_emergency_view(self, medical_tag):
        slug = medical_tag["slug"]
        r = requests.get(f"{BASE_URL}/api/finder/{slug}")
        assert r.status_code == 200
        html = r.text
        # red MEDICAL EMERGENCY ID pill
        assert 'data-testid="emergency-pill"' in html
        assert "MEDICAL EMERGENCY ID" in html
        # blood group O+
        assert "O+" in html
        # tel: link
        assert re.search(r'href="tel:\+91\d', html), "Missing tel:+91 link"
        assert 'data-testid="emergency-call-btn"' in html


# ---------- SSR unclaimed ----------
class TestSSRUnclaimed:
    def test_unclaimed_renders_claim_button(self, admin_session):
        # Create an unclaimed tag by directly inserting into Mongo via API: no such endpoint.
        # Instead, create a tag as admin then PATCH owner_id to null isn't allowed via API.
        # We use the DB via motor through a backend-internal admin trick — not available either.
        # Workaround: skip if we can't create unclaimed via API.
        # The seed in db.py creates one unclaimed tag? Check by enumerating slugs.
        # Try a known seeded unclaimed slug if any; else skip with informative msg.
        # Best-effort: create + PATCH via admin if API supports.
        slug_candidates = ["unclaimed-demo", "demo-unclaimed", "unclaimed"]
        found = None
        for s in slug_candidates:
            r = requests.get(f"{BASE_URL}/api/finder/{s}")
            if r.status_code == 200 and "finder-unclaimed" in r.text:
                found = s
                break
        if not found:
            pytest.skip("No unclaimed seed slug available; cannot create via public API")
        r = requests.get(f"{BASE_URL}/api/finder/{found}")
        assert r.status_code == 200
        html = r.text
        assert 'data-testid="finder-unclaimed"' in html
        assert 'data-testid="finder-claim-btn"' in html
        assert f'/claim/{found}' in html


# ---------- SSR not found ----------
class TestSSRNotFound:
    def test_404_renders_not_found_html(self):
        r = requests.get(f"{BASE_URL}/api/finder/this-does-not-exist-{uuid.uuid4().hex[:6]}")
        assert r.status_code == 404
        assert "text/html" in r.headers.get("content-type", "")
        assert 'data-testid="finder-not-found"' in r.text


# ---------- SSR action submission ----------
class TestSSRAction:
    def test_post_action_success_and_inbox(self, vehicle_tag, admin_session):
        slug = vehicle_tag["slug"]
        # ensure dedupe window cleared
        time.sleep(31)
        marker = f"SSR-TEST-{uuid.uuid4().hex[:8]}"
        r = requests.post(
            f"{BASE_URL}/api/finder/{slug}/action",
            data={"action_type": "wrong_parking", "lang": "en", "body": marker},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        assert 'data-testid="finder-thanks"' in r.text
        # inbox sees it
        time.sleep(0.3)
        inbox = admin_session.get(f"{BASE_URL}/api/inbox").json()
        bodies = [m.get("body", "") for m in inbox]
        assert any(marker in b for b in bodies), f"Marker {marker} not found in inbox"

    def test_honeypot_silently_drops(self, vehicle_tag, admin_session):
        slug = vehicle_tag["slug"]
        before = len(admin_session.get(f"{BASE_URL}/api/inbox").json())
        spam_marker = f"SPAM-{uuid.uuid4().hex[:8]}"
        r = requests.post(
            f"{BASE_URL}/api/finder/{slug}/action",
            data={
                "action_type": "wrong_parking",
                "lang": "en",
                "body": spam_marker,
                "bot_check": "spam",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        assert 'data-testid="finder-thanks"' in r.text
        time.sleep(0.3)
        inbox = admin_session.get(f"{BASE_URL}/api/inbox").json()
        bodies = [m.get("body", "") for m in inbox]
        assert spam_marker not in " ".join(bodies)
        # count unchanged (modulo any concurrent legit messages — should remain ≤ before)
        assert len(inbox) <= before + 0, f"Inbox grew despite honeypot: before={before} after={len(inbox)}"


# ---------- SSR scan dedupe ----------
class TestSSRScanDedupe:
    def test_rapid_scans_dedupe_within_30s(self, vehicle_tag, admin_session):
        slug = vehicle_tag["slug"]
        tag_id = vehicle_tag["id"]
        # baseline scan count
        time.sleep(31)  # clear any prior dedupe window
        # first scan kicks off
        requests.get(f"{BASE_URL}/api/finder/{slug}")
        time.sleep(0.5)
        before = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/activity").json().get("scan_count", 0)
        # 5 rapid scans
        for _ in range(5):
            requests.get(f"{BASE_URL}/api/finder/{slug}")
        time.sleep(0.5)
        after = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/activity").json().get("scan_count", 0)
        # within 30s dedupe window — increment should be 0 (already counted) or at most 1
        assert (after - before) <= 1, f"Scan dedupe broken: before={before} after={after}"


# ---------- QR PNG points to new finder URL ----------
class TestQRPointsToFinder:
    def test_qr_decodes_to_finder_url(self, vehicle_tag, admin_session):
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode
        except ImportError:
            pytest.skip("pyzbar/Pillow not installed")
        tag_id = vehicle_tag["id"]
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/qr.png")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        results = decode(img)
        assert results, "QR decode returned nothing"
        url = results[0].data.decode("utf-8")
        assert "/api/finder/" in url, f"QR encodes {url}, expected /api/finder/"
        assert vehicle_tag["slug"] in url
