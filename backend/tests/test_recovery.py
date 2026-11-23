"""In-process tests for recovery tracking (mongomock-motor, no services).

Covers: status transitions, token expiry + reuse, reminder logic,
high-priority alerts, the medical consent gate, and the core honesty rule —
nothing counts as recovered without the owner's own "yes".
"""
import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "infotag_test")
os.environ.setdefault("SITE_URL", "https://info-tag.test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import db as db_module
import recovery as rec
import routes.admin_routes as admin_routes
import routes.contact_routes as contact_routes
import routes.finder_ssr as finder_ssr
import routes.message_routes as message_routes
import routes.public_routes as public_routes
import routes.recovery_routes as recovery_routes
import routes.tag_routes as tag_routes

OWNER = {"id": "user_owner", "email": "owner@example.com", "phone": "+919800000001", "role": "user"}
OTHER = {"id": "user_other", "email": "other@example.com", "role": "user"}
NOW = "2026-11-01T10:00:00+00:00"


def _tag(tag_id, slug, type_="luggage", owner=OWNER["id"], status="active"):
    return {
        "id": tag_id, "slug": slug, "owner_id": owner, "type": type_, "label": slug,
        "display_name": f"Tag {slug}", "message": "", "status": status, "data": {},
        "public_fields": {"display_name": True, "message": True, "type": True},
        "created_at": NOW, "updated_at": NOW,
    }


@pytest.fixture()
def env(monkeypatch):
    mock_db = AsyncMongoMockClient()["infotag_test"]
    for mod in (db_module, admin_routes, contact_routes, finder_ssr, message_routes,
                public_routes, recovery_routes, tag_routes):
        monkeypatch.setattr(mod, "get_db", lambda: mock_db)

    sent = []

    def fake_notify(owner, subject, body, urgent=False):
        sent.append({"owner": (owner or {}).get("id"), "subject": subject, "body": body, "urgent": urgent})
        return {"email": True, "whatsapp": urgent, "sms": urgent}

    monkeypatch.setattr(rec, "notify_owner", fake_notify)
    # Existing finder alerts: silence them, they're not under test here.
    monkeypatch.setattr(message_routes, "notify_owner", lambda *a, **k: {})
    monkeypatch.setattr(finder_ssr, "notify_owner", lambda *a, **k: {})
    monkeypatch.setattr(contact_routes, "notify_owner", lambda *a, **k: {})

    app = FastAPI()
    for r in (tag_routes.router, message_routes.router, contact_routes.router, recovery_routes.router,
              public_routes.router, admin_routes.router, finder_ssr.router):
        app.include_router(r)
    current = {"user": OWNER}
    app.dependency_overrides[recovery_routes._current_user_dep] = lambda: current["user"]
    app.dependency_overrides[admin_routes._require_admin] = lambda: {"id": "admin", "role": "admin"}

    run = lambda coro: asyncio.run(coro)  # noqa: E731
    run(db_module.ensure_indexes(mock_db))
    run(mock_db.users.insert_many([dict(OWNER), dict(OTHER)]))
    run(mock_db.tags.insert_many([
        _tag("tag_bag", "bag1"),
        _tag("tag_pet", "pet1", "pet"),
        _tag("tag_med", "med1", "medical"),
        _tag("tag_car", "car1", "vehicle"),
    ]))
    return {"client": TestClient(app), "db": mock_db, "sent": sent, "run": run, "current": current}


def _case(env, tag_id):
    rows = env["run"](env["db"].recoveries.find({"tag_id": tag_id}, {"_id": 0}).sort("created_at", -1).to_list(5))
    return rows[0] if rows else None


def _token_from(msg):
    m = re.search(r"#t=([A-Za-z0-9_\-]+)", msg["body"])
    assert m, msg["body"]
    return m.group(1)


def _scan_and_message(env, slug, action="message", ip="1.2.3.4"):
    c = env["client"]
    assert c.get(f"/api/public/tags/{slug}", headers={"x-forwarded-for": ip}).status_code == 200
    r = c.post(f"/api/public/tags/{slug}/messages", json={"action_type": action, "body": "Found your bag"},
               headers={"x-forwarded-for": ip})
    assert r.status_code == 200, r.text


def _public_recovered(env):
    return env["client"].get("/api/public/stats").json()["items_recovered"]


# ---------------------------------------------------------------------------
# Event capture + status transitions
# ---------------------------------------------------------------------------
class TestEventCapture:
    def test_scan_opens_scanned_case_without_pii(self, env):
        env["client"].get("/api/public/tags/bag1", headers={"x-forwarded-for": "9.9.9.9"})
        case = _case(env, "tag_bag")
        assert case["status"] == "scanned"
        assert case["first_scan_at"] and case["scan_count"] == 1
        assert case["first_contact_at"] is None and case["resolved_at"] is None
        events = env["run"](env["db"].recovery_events.find({}, {"_id": 0}).to_list(10))
        assert [e["type"] for e in events] == ["scanned"]
        blob = repr(case) + repr(events)
        assert "9.9.9.9" not in blob and "ip_hash" not in blob

    def test_repeat_scan_reuses_case_and_dedupes(self, env):
        c = env["client"]
        c.get("/api/public/tags/bag1", headers={"x-forwarded-for": "1.1.1.1"})
        c.get("/api/public/tags/bag1", headers={"x-forwarded-for": "1.1.1.1"})  # deduped (30s)
        c.get("/api/public/tags/bag1", headers={"x-forwarded-for": "2.2.2.2"})
        assert env["run"](env["db"].recoveries.count_documents({})) == 1
        assert _case(env, "tag_bag")["scan_count"] == 2

    def test_contact_moves_to_awaiting_owner_and_prompts(self, env):
        _scan_and_message(env, "bag1")
        case = _case(env, "tag_bag")
        assert case["status"] == "awaiting_owner"
        assert case["first_contact_at"] and case["owner_prompted_at"]
        assert case["resolved_at"] is None
        prompts = [m for m in env["sent"] if not m["urgent"]]
        assert len(prompts) == 1
        body = prompts[0]["body"]
        for opt in ("हाँ, मिल गया", "नहीं मिला", "अभी नहीं"):
            assert opt in body
        assert "https://info-tag.test/recovery/confirm#t=" in body
        # Only the hash of the token is stored.
        token = _token_from(prompts[0])
        rows = env["run"](env["db"].recovery_tokens.find({}, {"_id": 0}).to_list(5))
        assert len(rows) == 1 and token not in repr(rows)

    def test_second_contact_does_not_reprompt(self, env):
        _scan_and_message(env, "bag1", ip="1.1.1.1")
        _scan_and_message(env, "bag1", ip="5.5.5.5")
        assert len(env["sent"]) == 1
        assert _case(env, "tag_bag")["contact_count"] == 2

    def test_callback_request_counts_as_contact(self, env):
        r = env["client"].post("/api/public/tags/bag1/call-request", json={"finder_phone": "+919811111111"})
        assert r.status_code == 200
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"

    def test_vehicle_actions_count_as_contact(self, env):
        _scan_and_message(env, "car1", action="wrong_parking")
        assert _case(env, "tag_car")["status"] == "awaiting_owner"

    def test_ssr_finder_page_and_action_are_tracked(self, env):
        c = env["client"]
        assert c.get("/api/finder/bag1", headers={"x-forwarded-for": "7.7.7.7"}).status_code == 200
        assert _case(env, "tag_bag")["status"] == "scanned"
        r = c.post("/api/finder/bag1/action", data={"action_type": "found", "lang": "hi"},
                   headers={"x-forwarded-for": "7.7.7.7"})
        assert r.status_code == 200
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"

    def test_unclaimed_tag_is_ignored(self, env):
        env["run"](env["db"].tags.insert_one(_tag("tag_free", "free1", owner=None)))
        env["client"].get("/api/public/tags/free1")
        assert _case(env, "tag_free") is None


# ---------------------------------------------------------------------------
# Token link — one-time, expiring
# ---------------------------------------------------------------------------
class TestTokenLink:
    def test_get_is_read_only_and_post_confirms(self, env):
        _scan_and_message(env, "bag1")
        token = _token_from(env["sent"][0])
        c = env["client"]
        info = c.get(f"/api/public/recovery/{token}")
        assert info.status_code == 200 and info.json()["status"] == "awaiting_owner"
        assert c.get(f"/api/public/recovery/{token}").status_code == 200  # GET never burns it
        r = c.post(f"/api/public/recovery/{token}", json={"answer": "found"})
        assert r.status_code == 200, r.text
        case = _case(env, "tag_bag")
        assert case["status"] == "owner_confirmed_found"
        assert case["resolved_at"] and case["resolution_source"] == "owner_link"

    def test_token_reuse_rejected(self, env):
        _scan_and_message(env, "bag1")
        token = _token_from(env["sent"][0])
        c = env["client"]
        assert c.post(f"/api/public/recovery/{token}", json={"answer": "not_yet"}).status_code == 200
        assert c.post(f"/api/public/recovery/{token}", json={"answer": "found"}).status_code == 409
        assert c.get(f"/api/public/recovery/{token}").status_code == 409
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"

    def test_expired_token_rejected(self, env):
        _scan_and_message(env, "bag1")
        token = _token_from(env["sent"][0])
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        env["run"](env["db"].recovery_tokens.update_many({}, {"$set": {"expires_at": past}}))
        c = env["client"]
        assert c.get(f"/api/public/recovery/{token}").status_code == 410
        assert c.post(f"/api/public/recovery/{token}", json={"answer": "found"}).status_code == 410
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"

    def test_unknown_token_and_bad_answer(self, env):
        c = env["client"]
        assert c.get("/api/public/recovery/nope").status_code == 404
        _scan_and_message(env, "bag1")
        token = _token_from(env["sent"][0])
        assert c.post(f"/api/public/recovery/{token}", json={"answer": "maybe"}).status_code == 422

    def test_final_answer_closes_other_links(self, env):
        _scan_and_message(env, "bag1")
        first = _token_from(env["sent"][0])
        env["run"](rec.sweep_due(env["db"], now=datetime.now(timezone.utc) + timedelta(hours=61)))
        second = _token_from(env["sent"][-1])
        assert first != second
        c = env["client"]
        assert c.post(f"/api/public/recovery/{second}", json={"answer": "not_found"}).status_code == 200
        assert c.post(f"/api/public/recovery/{first}", json={"answer": "found"}).status_code == 409


# ---------------------------------------------------------------------------
# Owner answers + dashboard
# ---------------------------------------------------------------------------
class TestOwnerResponses:
    def test_not_found_never_sets_resolved_at(self, env):
        _scan_and_message(env, "bag1")
        r = env["client"].post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "not_found"})
        assert r.status_code == 200
        case = _case(env, "tag_bag")
        assert case["status"] == "owner_not_found" and case["resolved_at"] is None

    def test_dashboard_pending_and_respond(self, env):
        _scan_and_message(env, "bag1")
        c = env["client"]
        pending = c.get("/api/recoveries/pending").json()
        assert len(pending) == 1 and pending[0]["tag_name"] == "Tag bag1"
        assert "finder" not in repr(pending).lower()
        r = c.post(f"/api/recoveries/{pending[0]['id']}/respond", json={"answer": "found"})
        assert r.status_code == 200
        assert _case(env, "tag_bag")["resolution_source"] == "owner_dashboard"
        assert c.get("/api/recoveries/pending").json() == []
        # Answering again is a conflict.
        assert c.post(f"/api/recoveries/{pending[0]['id']}/respond", json={"answer": "found"}).status_code == 409

    def test_other_user_cannot_respond(self, env):
        _scan_and_message(env, "bag1")
        env["current"]["user"] = OTHER
        c = env["client"]
        assert c.get("/api/recoveries/pending").json() == []
        r = c.post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})
        assert r.status_code == 404
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"

    def test_scan_only_case_cannot_be_confirmed(self, env):
        env["client"].get("/api/public/tags/bag1")
        r = env["client"].post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})
        assert r.status_code == 409
        assert _public_recovered(env) == 0

    def test_late_yes_after_probable_counts(self, env):
        _scan_and_message(env, "bag1")
        base = datetime.now(timezone.utc)
        for h in (61, 122, 183):
            env["run"](rec.sweep_due(env["db"], now=base + timedelta(hours=h)))
        assert _case(env, "tag_bag")["status"] == "probable_unconfirmed"
        pending = env["client"].get("/api/recoveries/pending").json()
        assert pending[0]["status"] == "probable_unconfirmed"
        env["client"].post(f"/api/recoveries/{pending[0]['id']}/respond", json={"answer": "found"})
        assert _case(env, "tag_bag")["status"] == "owner_confirmed_found"


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
class TestReminders:
    def test_reminder_then_final_then_probable(self, env):
        _scan_and_message(env, "bag1")
        base = datetime.now(timezone.utc)
        sweep = lambda h: env["run"](rec.sweep_due(env["db"], now=base + timedelta(hours=h)))  # noqa: E731

        assert sweep(24) == {"prompts": 0, "reminders": 0, "probable": 0}  # too early
        assert sweep(61)["reminders"] == 1
        case = _case(env, "tag_bag")
        assert case["reminder_count"] == 1 and case["last_reminder_at"]
        assert "Reminder" in env["sent"][-1]["subject"]

        assert sweep(61)["reminders"] == 0  # idempotent — no double send
        assert sweep(122)["reminders"] == 1
        assert _case(env, "tag_bag")["reminder_count"] == 2
        assert "Final reminder" in env["sent"][-1]["subject"]

        assert sweep(183)["probable"] == 1
        case = _case(env, "tag_bag")
        assert case["status"] == "probable_unconfirmed" and case["resolved_at"] is None
        assert sweep(500) == {"prompts": 0, "reminders": 0, "probable": 0}
        assert len(env["sent"]) == 3  # prompt + reminder + final, nothing more

    def test_not_yet_rearms_reminder(self, env):
        _scan_and_message(env, "bag1")
        token = _token_from(env["sent"][0])
        env["client"].post(f"/api/public/recovery/{token}", json={"answer": "not_yet"})
        case = _case(env, "tag_bag")
        assert case["status"] == "awaiting_owner" and case["owner_response"] == "not_yet"
        due = datetime.fromisoformat(case["next_action_at"])
        assert due - datetime.now(timezone.utc) > timedelta(hours=59)

    def test_answered_case_gets_no_reminders(self, env):
        _scan_and_message(env, "bag1")
        env["client"].post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})
        res = env["run"](rec.sweep_due(env["db"], now=datetime.now(timezone.utc) + timedelta(days=30)))
        assert res == {"prompts": 0, "reminders": 0, "probable": 0}

    def test_new_incident_after_close_opens_new_case(self, env):
        _scan_and_message(env, "bag1")
        env["client"].post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})
        _scan_and_message(env, "bag1", ip="8.8.8.8")
        assert env["run"](env["db"].recoveries.count_documents({"tag_id": "tag_bag"})) == 2
        assert _case(env, "tag_bag")["status"] == "awaiting_owner"


# ---------------------------------------------------------------------------
# High priority (child / pet / medical)
# ---------------------------------------------------------------------------
class TestHighPriority:
    def test_pet_gets_urgent_alert_then_delayed_safe_prompt(self, env):
        _scan_and_message(env, "pet1")
        assert len(env["sent"]) == 1 and env["sent"][0]["urgent"] is True
        assert "URGENT" in env["sent"][0]["subject"]
        case = _case(env, "tag_pet")
        assert case["status"] == "finder_contacted" and case["urgent_alert_at"] and case["priority"] == "high"

        base = datetime.now(timezone.utc)
        assert env["run"](rec.sweep_due(env["db"], now=base + timedelta(minutes=30)))["prompts"] == 0
        assert env["run"](rec.sweep_due(env["db"], now=base + timedelta(hours=3)))["prompts"] == 1
        prompt = env["sent"][-1]
        assert "found safe" in prompt["body"] and "सुरक्षित" in prompt["body"]
        assert _case(env, "tag_pet")["status"] == "awaiting_owner"

    def test_urgent_flag_forces_all_channels(self, monkeypatch):
        import notifications

        calls = []
        monkeypatch.setattr(notifications, "send_email", lambda *a: calls.append("email") or True)
        monkeypatch.setattr(notifications, "send_whatsapp", lambda *a: calls.append("wa") or True)
        monkeypatch.setattr(notifications, "send_sms", lambda *a: calls.append("sms") or True)
        owner = {"email": "o@x.in", "phone": "+919800000001", "whatsapp_alerts": False, "sms_alerts": False}
        notifications.notify_owner(owner, "s", "b")
        assert calls == ["email"]
        calls.clear()
        notifications.notify_owner(owner, "s", "b", urgent=True)
        assert calls == ["email", "wa", "sms"]

    def test_medical_consent_gating_unchanged(self, env):
        db = env["db"]
        env["run"](db.profiles.insert_one({"id": "p1", "tag_id": "tag_med", "emergency_mode": True, "consent_given": False,
                                           "blood_group": "O+", "emergency_contact_phone": "+919899999999"}))
        c = env["client"]
        # No consent → no medical data, neither JSON nor SSR.
        assert c.get("/api/public/tags/med1").json()["emergency"] is None
        assert "O+" not in c.get("/api/finder/med1", headers={"x-forwarded-for": "3.3.3.3"}).text
        # Consent → emergency view, and the scan is still tracked.
        env["run"](db.profiles.update_one({"id": "p1"}, {"$set": {"consent_given": True}}))
        assert c.get("/api/public/tags/med1", headers={"x-forwarded-for": "4.4.4.4"}).json()["emergency"]["blood_group"] == "O+"
        assert 'data-testid="emergency-root"' in c.get("/api/finder/med1", headers={"x-forwarded-for": "6.6.6.6"}).text
        assert _case(env, "tag_med")["status"] == "scanned"


# ---------------------------------------------------------------------------
# Honest counting
# ---------------------------------------------------------------------------
class TestCounting:
    def test_nothing_counts_as_recovered_without_owner_yes(self, env):
        _scan_and_message(env, "bag1")
        _scan_and_message(env, "car1", ip="2.2.2.2")
        base = datetime.now(timezone.utc)
        for h in (61, 122, 183):
            env["run"](rec.sweep_due(env["db"], now=base + timedelta(hours=h)))
        env["client"].post(f"/api/recoveries/{_case(env, 'tag_car')['id']}/respond", json={"answer": "not_found"})

        assert _public_recovered(env) == 0
        stats = env["client"].get("/api/admin/stats").json()
        r = stats["recovery"]
        assert r["confirmed_recoveries"] == 0
        assert r["probable_unconfirmed"] == 1
        assert r["owner_not_found"] == 1
        assert r["recovery_rate"] == 0
        assert stats["found"]["items_recovered"] == 0
        assert env["run"](env["db"].recoveries.count_documents({"resolved_at": {"$ne": None}})) == 0

    def test_admin_counts_separate_and_rate(self, env):
        c = env["client"]
        _scan_and_message(env, "bag1")
        _scan_and_message(env, "car1", ip="2.2.2.2")
        c.get("/api/public/tags/pet1", headers={"x-forwarded-for": "3.3.3.3"})  # scan only
        c.post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})

        r = c.get("/api/admin/stats").json()["recovery"]
        assert r["total_scans"] == 3
        assert r["finder_contacts"] == 2
        assert r["confirmed_recoveries"] == 1
        assert r["probable_unconfirmed"] == 0
        assert r["awaiting_owner"] == 1
        assert r["recovery_rate"] == 0.5
        assert "@" not in repr(r) and "+91" not in repr(r)

        daily = c.get("/api/admin/scans/daily?days=14").json()
        today = datetime.now(timezone.utc).date().isoformat()
        row = next(d for d in daily if d["day"] == today)
        assert row["count"] == 3 and row["recovered"] == 1

    def test_public_counter_includes_legacy_found_without_double_count(self, env):
        db = env["db"]
        env["run"](db.tags.insert_one(_tag("tag_old", "old1", status="found")))
        assert _public_recovered(env) == 1  # legacy manual "found"
        _scan_and_message(env, "bag1")
        env["client"].post(f"/api/recoveries/{_case(env, 'tag_bag')['id']}/respond", json={"answer": "found"})
        assert _public_recovered(env) == 2
        # Owner also flips the tag to "found" manually → still counted once.
        env["run"](db.tags.update_one({"id": "tag_bag"}, {"$set": {"status": "found"}}))
        assert _public_recovered(env) == 2

    def test_tag_delete_removes_recovery_data(self, env):
        _scan_and_message(env, "bag1")
        app = env["client"].app
        app.dependency_overrides[tag_routes._current_user_dep] = lambda: OWNER
        assert env["client"].delete("/api/tags/tag_bag").status_code == 200
        db = env["db"]
        assert env["run"](db.recoveries.count_documents({})) == 0
        assert env["run"](db.recovery_events.count_documents({})) == 0
        assert env["run"](db.recovery_tokens.count_documents({})) == 0
