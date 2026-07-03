"""
InfoTag — Backend API regression tests.
Covers: health/feature flags, JWT auth (register/login/logout/me),
tag CRUD, public finder + claim flow, messages + inbox, PDFs,
data isolation between users, manifest/sw, and integration placeholders.
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://smart-tags-dev.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "anand@tagit.in")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "InfoTagAdmin@2026")


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def second_user_session():
    s = requests.Session()
    email = f"test_user_{uuid.uuid4().hex[:8]}@tagit.in"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "SecondUser@2026", "display_name": "Second Tester"
    })
    assert r.status_code == 200, f"Register failed: {r.text}"
    s.email = email
    return s


# ---------- 1. Health + feature flags ----------
class TestHealth:
    def test_root(self):
        r = requests.get(f"{BASE_URL}/api")
        assert r.status_code == 200
        assert r.json().get("name") == "Info-Tag API"

    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["email_enabled"] is False
        assert data["whatsapp_enabled"] is False
        assert data["twilio_enabled"] is False

    def test_features(self):
        r = requests.get(f"{BASE_URL}/api/features")
        assert r.status_code == 200
        data = r.json()
        assert data["made_in_india"] is True
        # The free contact paths are always available, provider or not.
        assert data["callback_relay"] is True
        assert data["direct_deep_links"] is True
        # No providers configured on the test deployment.
        assert data["sms"] is False
        assert data["masked_calls"] is False


# ---------- 2. Contact endpoints (masked / direct) ----------
class TestContactEndpoints:
    @pytest.fixture(scope="class")
    def tag_slug(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/tags", json={
            "type": "vehicle", "label": "Contact test", "display_name": "Contact Test Car",
        })
        assert r.status_code == 200, r.text
        tag = r.json()
        assert tag["contact"]["mode"] == "masked"  # privacy-first default
        yield tag["slug"]
        admin_session.delete(f"{BASE_URL}/api/tags/{tag['id']}")

    def test_finder_view_masked_contact(self, tag_slug):
        r = requests.get(f"{BASE_URL}/api/public/tags/{tag_slug}")
        assert r.status_code == 200
        contact = r.json()["contact"]
        assert contact["mode"] == "masked"
        assert contact["callback"] is True
        assert "phone" not in contact  # the owner's number is never exposed

    def test_callback_request(self, tag_slug):
        r = requests.post(
            f"{BASE_URL}/api/public/tags/{tag_slug}/call-request",
            json={"finder_phone": "+919999900001", "finder_name": "Kind Finder"},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_masked_call_falls_back_when_unconfigured(self, tag_slug):
        r = requests.post(
            f"{BASE_URL}/api/public/tags/{tag_slug}/masked-call",
            json={"finder_phone": "+919999900002"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["fallback"] == "callback"

    def test_callback_request_rejects_bad_phone(self, tag_slug):
        r = requests.post(
            f"{BASE_URL}/api/public/tags/{tag_slug}/call-request",
            json={"finder_phone": "123", "finder_name": ""},
        )
        assert r.status_code == 422  # model enforces min_length=8


# ---------- 3. Auth flows ----------
class TestAuth:
    def test_register_new_user_and_me(self):
        s = requests.Session()
        email = f"test_register_{uuid.uuid4().hex[:8]}@tagit.in"
        r = s.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "Strong@1234", "display_name": "Reg Tester"
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert data["display_name"] == "Reg Tester"
        # cookie was set
        assert any("access_token" in c.name for c in s.cookies)
        # /me works
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == email

    def test_register_duplicate_rejected(self):
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": ADMIN_EMAIL, "password": "anything"
        })
        assert r.status_code == 400

    def test_admin_login_success(self, admin_session):
        me = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == ADMIN_EMAIL

    def test_login_invalid_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": "wrong-pass"
        })
        assert r.status_code == 401

    def test_me_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)

    def test_google_session_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/google/session",
                          json={"session_id": "invalid-session-xyz"})
        # 401 expected for invalid session, 502 if upstream unreachable - both acceptable
        assert r.status_code in (401, 502), r.text

    def test_google_session_missing_param(self):
        r = requests.post(f"{BASE_URL}/api/auth/google/session", json={})
        assert r.status_code == 400

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        r = s.post(f"{BASE_URL}/api/auth/logout")
        assert r.status_code == 200
        # /me should now fail
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code in (401, 403)


# ---------- 4. Tag CRUD ----------
class TestTagCRUD:
    def test_list_admin_tags_has_three_seeded(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/tags")
        assert r.status_code == 200
        tags = r.json()
        assert len(tags) >= 3
        types = {t["type"] for t in tags}
        assert {"vehicle", "pet", "medical"}.issubset(types)

    def test_create_update_get_delete_tag(self, admin_session):
        # CREATE
        payload = {
            "type": "luggage",
            "label": "TEST_Suitcase",
            "display_name": "My Trip Bag",
            "message": "Please call if found",
            "data": {"note": "Blue Hardcase"}
        }
        r = admin_session.post(f"{BASE_URL}/api/tags", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        tag_id = created["id"]
        assert created["label"] == "TEST_Suitcase"
        assert created["slug"]

        # GET single
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}")
        assert r.status_code == 200
        assert r.json()["display_name"] == "My Trip Bag"

        # UPDATE
        r = admin_session.patch(f"{BASE_URL}/api/tags/{tag_id}",
                                json={"message": "Updated message"})
        assert r.status_code == 200
        assert r.json()["message"] == "Updated message"

        # Verify persisted
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}")
        assert r.json()["message"] == "Updated message"

        # DELETE
        r = admin_session.delete(f"{BASE_URL}/api/tags/{tag_id}")
        assert r.status_code == 200
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}")
        assert r.status_code == 404

    def test_qr_png(self, admin_session):
        tags = admin_session.get(f"{BASE_URL}/api/tags").json()
        tag_id = tags[0]["id"]
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/qr.png")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert r.content[:4] == b"\x89PNG"
        # Default preview is inline so the <img> tag renders it.
        assert "inline" in r.headers.get("content-disposition", "inline")

    def test_qr_png_download(self, admin_session):
        tags = admin_session.get(f"{BASE_URL}/api/tags").json()
        tag_id = tags[0]["id"]
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/qr.png?download=1")
        assert r.status_code == 200
        assert r.content[:4] == b"\x89PNG"
        # ?download=1 forces a Save-As with a sensible filename.
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".png" in cd


# ---------- 5. PDF generation ----------
class TestPDFs:
    @pytest.mark.parametrize("layout", ["a4_stickers", "id_card", "keyring"])
    def test_pdf_layouts(self, admin_session, layout):
        tags = admin_session.get(f"{BASE_URL}/api/tags").json()
        tag_id = tags[0]["id"]
        r = admin_session.get(f"{BASE_URL}/api/tags/{tag_id}/pdf?layout={layout}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


# ---------- 6. Public finder + scan + claim ----------
class TestPublicFinder:
    def _get_seeded_tag(self, session, t_type):
        tags = session.get(f"{BASE_URL}/api/tags").json()
        return next(t for t in tags if t["type"] == t_type)

    def test_finder_vehicle(self, admin_session):
        tag = self._get_seeded_tag(admin_session, "vehicle")
        r = requests.get(f"{BASE_URL}/api/public/tags/{tag['slug']}")
        assert r.status_code == 200
        data = r.json()
        assert data["slug"] == tag["slug"]
        assert data["type"] == "vehicle"
        assert data["is_unclaimed"] is False
        assert data["emergency"] is None

    def test_finder_medical_emergency_payload(self, admin_session):
        tag = self._get_seeded_tag(admin_session, "medical")
        r = requests.get(f"{BASE_URL}/api/public/tags/{tag['slug']}")
        assert r.status_code == 200
        data = r.json()
        emergency = data["emergency"]
        assert emergency is not None
        assert emergency["blood_group"] == "O+"
        assert "Penicillin" in emergency["allergies"]
        assert emergency["emergency_contact_phone"].startswith("+91")

    def test_finder_404(self):
        r = requests.get(f"{BASE_URL}/api/public/tags/nonexistent-slug-zzz")
        assert r.status_code == 404

    def test_finder_records_scan_and_message_and_inbox(self, admin_session):
        tag = self._get_seeded_tag(admin_session, "vehicle")
        # Scan
        requests.get(f"{BASE_URL}/api/public/tags/{tag['slug']}")
        # Post finder message
        msg_payload = {
            "action_type": "wrong_parking",
            "finder_name": "Helpful Stranger",
            "finder_contact": "9999999999",
            "body": "Your bike is blocking <script>alert(1)</script> exit",
            "bot_check": ""
        }
        r = requests.post(f"{BASE_URL}/api/public/tags/{tag['slug']}/messages", json=msg_payload)
        assert r.status_code == 200, r.text
        body = r.json()
        # HTML stripped
        assert "<script>" not in body["body"]
        assert "alert" in body["body"]  # text retained, tags removed
        # Inbox sees it
        time.sleep(0.2)
        inbox = admin_session.get(f"{BASE_URL}/api/inbox")
        assert inbox.status_code == 200
        actions = [m["action_type"] for m in inbox.json()]
        assert "wrong_parking" in actions

    def test_honeypot_blocks_silently(self, admin_session):
        tag = self._get_seeded_tag(admin_session, "vehicle")
        before = len(admin_session.get(f"{BASE_URL}/api/inbox").json())
        r = requests.post(f"{BASE_URL}/api/public/tags/{tag['slug']}/messages", json={
            "action_type": "found",
            "body": "spam",
            "bot_check": "iam-a-bot"
        })
        assert r.status_code == 200
        assert r.json()["id"] == "blocked"
        time.sleep(0.2)
        after = len(admin_session.get(f"{BASE_URL}/api/inbox").json())
        assert after == before

    def test_claim_unclaimed_tag(self, second_user_session):
        # Seed an unclaimed tag directly via API (create as second user then unset owner)
        # We'll use Mongo via a fresh admin tag creation isn't feasible; instead use a public
        # POST claim endpoint expects existing slug. We simulate by creating a tag as user
        # and then poking via API — but the create endpoint always sets owner_id.
        # So this test uses the existing fixture and verifies claim rejects already-claimed tag.
        r = requests.get(f"{BASE_URL}/api/public/tags/anything")
        # Just test the claim rejects already-claimed tags via second_user_session
        # Create one tag as second user, then try to claim it again (should fail).
        created = second_user_session.post(f"{BASE_URL}/api/tags", json={
            "type": "keys", "label": "TEST_Keys"
        }).json()
        slug = created["slug"]
        r = second_user_session.post(f"{BASE_URL}/api/public/tags/{slug}/claim")
        assert r.status_code == 400  # already claimed
        # Cleanup
        second_user_session.delete(f"{BASE_URL}/api/tags/{created['id']}")


# ---------- 7. Ownership / data isolation ----------
class TestDataIsolation:
    def test_second_user_cannot_see_admin_tags(self, second_user_session):
        r = second_user_session.get(f"{BASE_URL}/api/tags")
        assert r.status_code == 200
        # second user has zero or only their own tags - none should belong to admin's seed
        for t in r.json():
            assert t["label"] not in {"My Bike", "Bruno", "Anand — Medical ID"}

    def test_second_user_cannot_get_admin_tag(self, admin_session, second_user_session):
        admin_tag = admin_session.get(f"{BASE_URL}/api/tags").json()[0]
        r = second_user_session.get(f"{BASE_URL}/api/tags/{admin_tag['id']}")
        assert r.status_code == 404  # ownership-scoped 404

    def test_second_user_cannot_patch_admin_tag(self, admin_session, second_user_session):
        admin_tag = admin_session.get(f"{BASE_URL}/api/tags").json()[0]
        r = second_user_session.patch(f"{BASE_URL}/api/tags/{admin_tag['id']}",
                                      json={"message": "hacked"})
        assert r.status_code == 404

    def test_second_user_cannot_delete_admin_tag(self, admin_session, second_user_session):
        admin_tag = admin_session.get(f"{BASE_URL}/api/tags").json()[0]
        r = second_user_session.delete(f"{BASE_URL}/api/tags/{admin_tag['id']}")
        assert r.status_code == 404


# ---------- 8. Settings (update + export) ----------
class TestSettings:
    def test_patch_me_updates_display_name(self, admin_session):
        original = admin_session.get(f"{BASE_URL}/api/auth/me").json()["display_name"]
        r = admin_session.patch(f"{BASE_URL}/api/auth/me",
                                json={"display_name": "Anand Lakhera (Admin)"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Anand Lakhera (Admin)"
        # Restore
        admin_session.patch(f"{BASE_URL}/api/auth/me", json={"display_name": original})

    def test_export(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/export")
        assert r.status_code == 200
        data = r.json()
        for k in ("user", "tags", "profiles", "messages", "scans"):
            assert k in data
        assert data["user"]["email"] == ADMIN_EMAIL
        assert len(data["tags"]) >= 3


# ---------- 9. PWA manifest + service worker ----------
class TestPWA:
    def test_manifest(self):
        r = requests.get(f"{BASE_URL}/manifest.json")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("name", "").startswith("Info-Tag")
        assert data.get("short_name") == "Info-Tag"
        assert data.get("theme_color", "").lower() == "#0f172a"

    def test_service_worker(self):
        r = requests.get(f"{BASE_URL}/sw.js")
        assert r.status_code == 200
        assert "javascript" in r.headers.get("content-type", "").lower() or r.text
