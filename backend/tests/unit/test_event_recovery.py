"""Event Mode × Recovery tracking.

* Event guests (no account) get the owner confirmation prompt on free
  channels only, with no "dashboard" hint.
* An organiser's help-desk "mark returned" is NOT an owner confirmation and
  never reaches the public recovered counter.
* A guest's own "I got my item back" (private Digital ID link) confirms an
  open case — but only if a finder actually reached out.
"""
import re

import pytest

import recovery as rec
from tests.unit.test_event_api import _claim, _create_event, _path, _setup_org, _tag_urls


@pytest.fixture
def sent(monkeypatch):
    out = []

    def fake_notify(owner, subject, body, urgent=False):
        out.append({"owner": owner, "subject": subject, "body": body, "urgent": urgent})
        return {"email": True, "whatsapp": False, "sms": False}

    monkeypatch.setattr(rec, "notify_owner", fake_notify)
    return out


async def _claimed_tag(client, db, admin, org, **claim_over):
    ev = await _create_event(admin, org["id"], count=5)
    t0 = (await _tag_urls(admin, ev["id"], 1))[0]
    r = await _claim(client, t0["tag_url"], email="asha@example.com", **claim_over)
    assert r.status_code == 200, r.text
    tag = await db.tags.find_one({"event_id": ev["id"]}, {"_id": 0})
    k = re.search(r"/id/[A-Z2-7]+\?k=([\w-]+)", r.text).group(1)
    return ev, t0, tag, k


async def _case(db, tag_id):
    rows = await db.recoveries.find({"tag_id": tag_id}, {"_id": 0}).sort("created_at", -1).to_list(1)
    return rows[0] if rows else None


async def _public_recovered(client):
    return (await client.get("/api/public/stats")).json()["items_recovered"]


async def test_event_scan_and_finder_contact_prompt_guest(client, db, sent):
    admin, _, org = await _setup_org(client, db)
    ev, t0, tag, _ = await _claimed_tag(client, db, admin, org)

    await client.get(_path(t0["tag_url"]))
    case = await _case(db, tag["id"])
    assert case and case["status"] == "scanned" and case["owner_id"].startswith("guest_")

    r = await client.post(f"/api/finder/{tag['slug']}/action", data={"action_type": "found", "lang": "en"})
    assert r.status_code == 200
    case = await _case(db, tag["id"])
    assert case["status"] == "awaiting_owner"

    prompts = [m for m in sent if "Did you get your item back" in m["subject"]]
    assert len(prompts) == 1
    p = prompts[0]
    assert p["owner"]["_free_only"] is True and p["owner"]["sms_alerts"] is False
    assert "dashboard" not in p["body"].lower()  # guests have no dashboard
    assert "/recovery/confirm#t=" in p["body"]


async def test_organiser_mark_returned_is_not_a_recovery(client, db, sent):
    admin, organizer, org = await _setup_org(client, db)
    ev, t0, tag, _ = await _claimed_tag(client, db, admin, org)
    await client.post(f"/api/finder/{tag['slug']}/action", data={"action_type": "found", "lang": "en"})

    r = await organizer.post(f"/api/events/{ev['id']}/tags/{tag['serial']}/returned", json={"returned": True})
    assert r.status_code == 200, r.text
    assert (await db.tags.find_one({"id": tag["id"]}))["status"] == "found"

    assert (await _case(db, tag["id"]))["status"] == "awaiting_owner"
    assert await _public_recovered(client) == 0
    stats = (await admin.get("/api/admin/stats")).json()["recovery"]
    assert stats["confirmed_recoveries"] == 0 and stats["legacy_manual_found"] == 0


async def test_guest_digital_id_return_confirms_open_case(client, db, sent):
    admin, _, org = await _setup_org(client, db)
    ev, t0, tag, k = await _claimed_tag(client, db, admin, org)
    await client.post(f"/api/finder/{tag['slug']}/action", data={"action_type": "message", "lang": "en", "body": "hi"})

    r = await client.post(_path(t0["digital_id_url"]) + "/returned", data={"k": k}, follow_redirects=False)
    assert r.status_code == 303
    case = await _case(db, tag["id"])
    assert case["status"] == "owner_confirmed_found"
    assert case["resolution_source"] == "owner_digital_id" and case["resolved_at"]
    assert await _public_recovered(client) == 1


async def test_guest_return_without_finder_contact_counts_nothing(client, db, sent):
    admin, _, org = await _setup_org(client, db)
    ev, t0, tag, k = await _claimed_tag(client, db, admin, org)
    await client.get(_path(t0["tag_url"]))  # scan only, no finder contact

    r = await client.post(_path(t0["digital_id_url"]) + "/returned", data={"k": k}, follow_redirects=False)
    assert r.status_code == 303
    assert (await _case(db, tag["id"]))["status"] == "scanned"
    assert await _public_recovered(client) == 0
