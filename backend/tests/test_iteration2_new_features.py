"""
InfoTag — Iteration-2 new-features tests.

Covers ONLY what changed in this iteration (per review request):
  - Scan dedupe within 30s
  - Lifespan migration (sanity via /api/health)
  - DELETE /api/auth/me requires current_password (password user)
  - Sponsor endpoint + stats + honeypot + 422 validation
Plus a small sanity subset of older flows to ensure nothing regressed.
"""
import os
import time
import uuid
import asyncio
import concurrent.futures as cf
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://smart-tags-dev.preview.emergentagent.com"
).rstrip("/")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "anand@tagit.in")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "InfoTagAdmin@2026")


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_tags(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/tags")
    assert r.status_code == 200
    tags = r.json()
    assert len(tags) >= 3, f"Expected at least 3 demo tags, got {len(tags)}"
    return tags


# ---------- Sanity subset of older flows ----------
class TestSanityOldFlows:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_admin_login_and_three_tags(self, admin_tags):
        # 3 demo tags pre-seeded
        types = sorted(t["type"] for t in admin_tags)
        assert "medical" in types
        assert "pet" in types
        assert "vehicle" in types

    def test_public_finder_returns_200(self, admin_tags):
        slug = admin_tags[0]["slug"]
        r = requests.get(f"{BASE_URL}/api/public/tags/{slug}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["slug"] == slug

    def test_emergency_block_on_medical_tag(self, admin_tags):
        med = next(t for t in admin_tags if t["type"] == "medical")
        r = requests.get(f"{BASE_URL}/api/public/tags/{med['slug']}")
        assert r.status_code == 200
        data = r.json()
        assert data.get("emergency") is not None, "Medical tag should expose emergency block"
        assert "blood_group" in data["emergency"]

    def test_inbox_works(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/inbox")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Scan dedupe within 30s ----------
class TestScanDedupe:
    def test_repeat_scans_within_30s_increment_by_one(self, admin_session):
        # Create a FRESH tag so no prior scan from this IP exists inside the
        # 30s dedupe window — otherwise the test result depends on whatever
        # else hit the seeded tag in the last 30 seconds.
        create = admin_session.post(
            f"{BASE_URL}/api/tags",
            json={"type": "general", "label": "Scan-dedupe test"},
        )
        assert create.status_code == 200, create.text
        tag = create.json()
        tag_id = tag["id"]
        slug = tag["slug"]

        before = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/activity").json()
        before_count = before["scan_count"]

        # Fire 5 GETs as the same client (same IP from the public ingress)
        for _ in range(5):
            r = requests.get(f"{BASE_URL}/api/public/tags/{slug}")
            assert r.status_code == 200

        # Give Mongo a moment
        time.sleep(1)
        after = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/activity").json()
        after_count = after["scan_count"]

        delta = after_count - before_count
        assert delta == 1, (
            f"Expected scan_count to increase by exactly 1 within 30s window, "
            f"but increased by {delta} ({before_count} -> {after_count}). "
            f"Dedupe logic appears to be missing from GET /api/public/tags/{{slug}}."
        )

        # Cleanup so we don't pollute the admin's tag list across reruns
        admin_session.delete(f"{BASE_URL}/api/tags/{tag_id}")


# ---------- DELETE /api/auth/me requires current_password ----------
class TestRightToBeForgotten:
    def _signup(self):
        s = requests.Session()
        email = f"rtbf_{uuid.uuid4().hex[:8]}@tagit.in"
        pwd = "Rtbf@2026!"
        r = s.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": pwd, "display_name": "RTBF"},
        )
        assert r.status_code == 200, r.text
        return s, email, pwd

    def test_delete_without_body_returns_400(self):
        s, email, _ = self._signup()
        # Use a raw request with NO body to mimic the failing case
        r = s.delete(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        assert "current password" in r.text.lower()

        # User must still exist
        r2 = s.get(f"{BASE_URL}/api/auth/me")
        assert r2.status_code == 200

    def test_delete_with_wrong_password_returns_400(self):
        s, email, _ = self._signup()
        r = s.delete(f"{BASE_URL}/api/auth/me", json={"current_password": "WrongPass1!"})
        assert r.status_code == 400
        r2 = s.get(f"{BASE_URL}/api/auth/me")
        assert r2.status_code == 200

    def test_delete_with_correct_password_succeeds(self):
        s, email, pwd = self._signup()
        r = s.delete(f"{BASE_URL}/api/auth/me", json={"current_password": pwd})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Subsequent /me must be 401
        r2 = s.get(f"{BASE_URL}/api/auth/me")
        assert r2.status_code == 401


# ---------- Sponsor endpoint ----------
class TestSponsor:
    def test_stats_baseline(self):
        r = requests.get(f"{BASE_URL}/api/sponsors/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_pledged" in data and "sponsor_count" in data
        assert isinstance(data["total_pledged"], int)
        assert isinstance(data["sponsor_count"], int)

    def test_submit_creates_doc(self):
        before = requests.get(f"{BASE_URL}/api/sponsors/stats").json()
        payload = {
            "name": "TEST_Sponsor",
            "email": f"TEST_sponsor_{uuid.uuid4().hex[:6]}@tagit.in",
            "tag_count": 50,
            "message": "Happy to fund 50 stickers",
        }
        r = requests.post(f"{BASE_URL}/api/sponsors", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["id"].startswith("spon_")

        after = requests.get(f"{BASE_URL}/api/sponsors/stats").json()
        assert after["sponsor_count"] == before["sponsor_count"] + 1
        assert after["total_pledged"] == before["total_pledged"] + 50

    def test_honeypot_does_not_create_doc(self):
        before = requests.get(f"{BASE_URL}/api/sponsors/stats").json()
        payload = {
            "name": "TEST_Bot",
            "email": f"TEST_bot_{uuid.uuid4().hex[:6]}@tagit.in",
            "tag_count": 10,
            "message": "bot",
            "bot_check": "i am a bot",
        }
        r = requests.post(f"{BASE_URL}/api/sponsors", json=payload)
        # honeypot should silently return ok=true
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        # Stats should NOT change
        after = requests.get(f"{BASE_URL}/api/sponsors/stats").json()
        assert after["sponsor_count"] == before["sponsor_count"]
        assert after["total_pledged"] == before["total_pledged"]

    def test_validation_missing_fields(self):
        # Missing name
        r = requests.post(
            f"{BASE_URL}/api/sponsors",
            json={"email": "x@y.com", "tag_count": 5},
        )
        assert r.status_code == 422, r.text
        # Missing email
        r2 = requests.post(
            f"{BASE_URL}/api/sponsors",
            json={"name": "x", "tag_count": 5},
        )
        assert r2.status_code == 422
        # Missing tag_count
        r3 = requests.post(
            f"{BASE_URL}/api/sponsors",
            json={"name": "x", "email": "x@y.com"},
        )
        assert r3.status_code == 422
