import re

import pytest

from tests.unit.conftest import login, make_user


async def _setup_org(client, db, can_generate=False):
    await make_user(db, "admin@x.in", role="admin")
    admin = await login(client, "admin@x.in")
    r = await admin.post("/api/admin/orgs", json={"name": "Parikrma Samiti", "can_generate": can_generate, "max_tags_per_event": 500})
    assert r.status_code == 200, r.text
    org = r.json()
    r = await admin.post(f"/api/admin/orgs/{org['id']}/members", json={"email": "org@x.in", "display_name": "Samiti"})
    assert r.status_code == 200, r.text
    creds = r.json()
    assert creds["password"] and len(creds["password"]) == 19
    organizer = await login(client, "org@x.in", creds["password"])
    return admin, organizer, org


async def _create_event(admin, org_id=None, count=200, output_type="sticker_sheet", code="PK24"):
    r = await admin.post("/api/events", json={
        "org_id": org_id, "name": "Prathivi Parikrma", "code": code, "date": "2026-11-24",
        "venue": "Ujjain", "tag_count": count, "output_type": output_type,
        "reward_text": "Sweets!", "help_desk_note": "Lost & Found desk: Gate 2",
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _tag_urls(admin, event_id, n=5, from_serial=0):
    r = await admin.get(f"/api/events/{event_id}/tags", params={"from_serial": from_serial, "limit": n})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _path(url):
    return re.sub(r"^https?://[^/]+", "", url)


async def _claim(client, tag_url, **over):
    form = {"name": "Asha", "phone": "9876543210", "email": "", "item_type": "bag",
            "contact_mode": "masked", "wa_opt_in": "1", "consent": "1", "lang": "en"}
    form.update(over)
    return await client.post(_path(tag_url) + "/claim", data=form)


async def test_organizer_sees_only_their_events(client, db):
    admin, organizer, org = await _setup_org(client, db)
    mine = await _create_event(admin, org["id"], count=10)
    other = await _create_event(admin, None, count=10, code="OTH1")

    r = await organizer.get("/api/events")
    ids = [e["id"] for e in r.json()["items"]]
    assert ids == [mine["id"]]
    assert (await organizer.get(f"/api/events/{other['id']}")).status_code == 404
    assert (await organizer.get(f"/api/events/{other['id']}/print.pdf")).status_code == 404
    assert (await organizer.get(f"/api/events/{mine['id']}")).status_code == 200
    # admin-only areas stay closed
    assert (await organizer.get("/api/admin/orgs")).status_code == 403
    assert (await organizer.post(f"/api/events/{mine['id']}/batches/1/revoke", json={})).status_code == 403
    # can't create without can_generate
    r = await organizer.post("/api/events", json={"name": "Mela", "tag_count": 5})
    assert r.status_code == 403
    # plain users have no access at all
    await make_user(db, "u@x.in")
    user = await login(client, "u@x.in")
    assert (await user.get("/api/events")).status_code == 403


async def test_organizer_with_generate_rights_is_capped(client, db):
    admin, organizer, org = await _setup_org(client, db, can_generate=True)
    r = await organizer.post("/api/events", json={"name": "Mela", "tag_count": 501})
    assert r.status_code == 400
    r = await organizer.post("/api/events", json={"name": "Mela", "tag_count": 50, "org_id": "org_spoofed"})
    assert r.status_code == 200 and r.json()["org_id"] == org["id"]
    meta = (await organizer.get("/api/events/meta")).json()
    assert meta["can_create"] and not meta["can_revoke"]


async def test_no_rows_until_claim_then_claim_flow(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=200)
    assert ev["stats"]["generated"] == 200
    assert await db.tags.count_documents({"event_id": ev["id"]}) == 0  # signed tokens, no rows

    tags = await _tag_urls(admin, ev["id"], 3)
    page = await client.get(_path(tags[0]["tag_url"]))
    assert page.status_code == 200 and 'data-testid="event-claim"' in page.text
    assert "9876543210" not in page.text

    r = await _claim(client, tags[0]["tag_url"])
    assert r.status_code == 200, r.text
    assert 'data-testid="claim-success"' in r.text
    assert await db.tags.count_documents({"event_id": ev["id"]}) == 1
    tag = await db.tags.find_one({"event_id": ev["id"]})
    assert tag["type"] == "general" and tag["owner_id"].startswith("guest_")
    assert tag["contact"]["mode"] == "masked"

    # after claim the same QR shows the finder page — number stays hidden
    page = await client.get(_path(tags[0]["tag_url"]))
    assert 'data-testid="finder-claimed"' in page.text
    assert "9876543210" not in page.text
    assert "Sweets!" in page.text and "Gate 2" in page.text

    # second claim of the same sticker is refused
    r = await _claim(client, tags[0]["tag_url"], name="Mallory")
    assert 'data-testid="finder-claimed"' in r.text or r.status_code == 409
    assert await db.tags.count_documents({"event_id": ev["id"]}) == 1

    detail = (await admin.get(f"/api/events/{ev['id']}")).json()
    assert detail["stats"]["claimed"] == 1 and detail["stats"]["owners"] == 1
    assert detail["stats"]["scans"] >= 1


async def test_claim_validation(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=5)
    url = (await _tag_urls(admin, ev["id"], 1))[0]["tag_url"]
    r = await _claim(client, url, phone="", email="")
    assert r.status_code == 400 and "claim-error" in r.text
    r = await _claim(client, url, consent="")
    assert r.status_code == 400
    r = await _claim(client, url, phone="", email="a@b.co", contact_mode="direct")
    assert r.status_code == 400
    assert await db.tags.count_documents({}) == 0


async def test_finder_message_alerts_and_counts(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=5)
    url = (await _tag_urls(admin, ev["id"], 1))[0]["tag_url"]
    await _claim(client, url)
    tag = await db.tags.find_one({"event_id": ev["id"]})
    r = await client.post(f"/api/finder/{tag['slug']}/action", data={"action_type": "found", "lang": "en", "body": "found it"})
    assert r.status_code == 200
    assert await db.messages.count_documents({"tag_id": tag["id"]}) == 1
    detail = (await admin.get(f"/api/events/{ev['id']}")).json()
    assert detail["stats"]["found"] == 1


async def test_guest_pack_claims_all_four(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=8, output_type="guest_pack")
    assert ev["pack_size"] == 4
    tags = await _tag_urls(admin, ev["id"], 8)
    r = await _claim(client, tags[2]["tag_url"], item_type="bottle")
    assert r.status_code == 200
    rows = await db.tags.find({"event_id": ev["id"]}).to_list(10)
    assert sorted(t["serial"] for t in rows) == [0, 1, 2, 3]
    assert len({t["owner_id"] for t in rows}) == 1
    assert {t["serial"]: t["data"]["item_type"] for t in rows}[2] == "bottle"
    # another sticker of the same pack is already claimed
    page = await client.get(_path(tags[1]["tag_url"]))
    assert 'data-testid="finder-claimed"' in page.text
    # the next guest's pack is still free
    page = await client.get(_path(tags[4]["tag_url"]))
    assert 'data-testid="event-claim"' in page.text
    pdf = await admin.get(f"/api/events/{ev['id']}/print.pdf", params={"from_serial": 0, "count": 8})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_short_code_lookup_and_legacy_slugs(client, db):
    admin, organizer, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=5)
    t0 = (await _tag_urls(admin, ev["id"], 1))[0]
    r = await client.get(f"/c/{t0['code'].lower()}", follow_redirects=False)
    assert r.status_code == 302 and "/t/" in r.headers["location"]
    bad = t0["code"][:-1] + ("A" if t0["code"][-1] != "A" else "B")
    assert (await client.get(f"/c/{bad}")).status_code == 404
    r = await organizer.get(f"/api/events/{ev['id']}/lookup", params={"code": t0["code"]})
    assert r.status_code == 200 and r.json()["serial"] == 0
    # legacy slug-based tags keep working through the short paths
    await db.tags.insert_one({"id": "tag_legacy", "slug": "Ab3dE9x", "owner_id": "user_1", "type": "pet"})
    r = await client.get("/t/Ab3dE9x", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("/api/finder/Ab3dE9x")


async def test_revoke_and_restore(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=10)
    tags = await _tag_urls(admin, ev["id"], 3)
    bid = tags[0]["batch_bid"]
    r = await admin.post(f"/api/events/{ev['id']}/batches/{bid}/revoke", json={"from_serial": 1, "to_serial": 1})
    assert r.status_code == 200
    assert (await client.get(_path(tags[1]["tag_url"]))).status_code == 410
    assert (await client.get(_path(tags[0]["tag_url"]))).status_code == 200
    await admin.post(f"/api/events/{ev['id']}/batches/{bid}/revoke", json={})
    assert (await client.get(_path(tags[0]["tag_url"]))).status_code == 410
    await admin.post(f"/api/events/{ev['id']}/batches/{bid}/restore")
    assert (await client.get(_path(tags[0]["tag_url"]))).status_code == 200


async def test_spares_digital_ids_and_exports(client, db):
    admin, organizer, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=20)
    r = await admin.post(f"/api/events/{ev['id']}/batches", json={"percent": 10})
    assert r.status_code == 200 and r.json()["count"] == 2 and r.json()["serial_start"] == 20
    man = (await organizer.get(f"/api/events/{ev['id']}/print/manifest")).json()
    assert sum(c["count"] for c in man["chunks"]) == 22

    t0 = (await _tag_urls(organizer, ev["id"], 1))[0]
    page = await client.get(_path(t0["digital_id_url"]))
    assert page.status_code == 200 and 'data-testid="digital-id-card"' in page.text and "id-claim" in page.text

    r = await _claim(client, t0["tag_url"])
    k = re.search(r"/id/[A-Z2-7]+\?k=([\w-]+)", r.text).group(1)
    page = await client.get(_path(t0["digital_id_url"]) + f"?k={k}")
    assert "Asha" in page.text and "id-returned" in page.text
    page = await client.get(_path(t0["digital_id_url"]))
    assert "Asha" not in page.text  # holder name only with the manage key
    r = await client.post(_path(t0["digital_id_url"]) + "/returned", data={"k": k}, follow_redirects=False)
    assert r.status_code == 303
    assert (await admin.get(f"/api/events/{ev['id']}")).json()["stats"]["returned"] == 1

    csv_text = (await organizer.get(f"/api/events/{ev['id']}/report.csv")).text
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("serial,code") and len(lines) == 23
    assert "Asha" not in csv_text and "9876543210" not in csv_text
    assert "Asha" in (await organizer.get(f"/api/events/{ev['id']}/report.csv", params={"include_names": 1})).text
    ids = (await organizer.get(f"/api/events/{ev['id']}/digital-ids.csv")).text
    assert ids.count("/id/") == 22


async def test_print_endpoints(client, db):
    admin, organizer, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=30)
    r = await organizer.get(f"/api/events/{ev['id']}/print.pdf", params={"preset": "a4_35", "start_slot": 3, "cut_marks": 1})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = await organizer.get(f"/api/events/{ev['id']}/print.pdf", params={"preset": "a4_24", "qr_mm": 10})
    assert r.status_code == 400
    r = await organizer.get(f"/api/events/{ev['id']}/print.pdf", params={"count": 251})
    assert r.status_code == 422
    r = await organizer.get(f"/api/events/{ev['id']}/print.pdf", params={"mode": "badge_cards"})
    assert r.status_code == 200
    assert (await organizer.get(f"/api/events/{ev['id']}/poster.pdf")).status_code == 200
    assert (await organizer.get("/api/events/print/calibration.pdf", params={"preset": "a4_24", "offset_x": 1})).status_code == 200
    page = await client.get("/e/PK24")
    assert page.status_code == 200 and "Gate 2" in page.text


async def test_shared_ip_crowd_is_not_blocked(client, db):
    """200 guests behind one venue IP must all be able to claim."""
    import httpx

    from server import app

    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=200)
    tags = await _tag_urls(admin, ev["id"], 200)
    ok = 0
    for i, t in enumerate(tags[:200]):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://info-tag.test",
                                     headers={"x-forwarded-for": "203.0.113.7"}) as phone:
            await phone.get(_path(t["tag_url"]))  # gets its own anonymous cookie
            r = await _claim(phone, t["tag_url"], name=f"Guest {i}")
            ok += r.status_code == 200
    assert ok == 200


async def test_one_client_spamming_is_limited(client, db):
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=20)
    url = (await _tag_urls(admin, ev["id"], 1))[0]["tag_url"]
    await client.get(_path(url))
    codes = [(await _claim(client, url, phone="", email="")).status_code for _ in range(12)]
    assert 429 in codes


@pytest.mark.parametrize("bad", ["", "ZZZZ", "A" * 28])
async def test_unknown_tokens_404(client, db, bad):
    r = await client.get(f"/t/{bad}") if bad else await client.get("/t/x")
    assert r.status_code == 404


async def test_uppercase_qr_paths_and_csv_injection(client, db):
    """Printed QRs use /T/ and /E/ (alphanumeric mode) — both must resolve."""
    admin, organizer, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=3)
    t0 = (await _tag_urls(admin, ev["id"], 1))[0]
    token = t0["tag_url"].rsplit("/", 1)[1]
    r = await client.get(f"/T/{token}")
    assert r.status_code == 200 and 'data-testid="event-claim"' in r.text
    assert (await client.get("/E/PK24")).status_code == 200
    await _claim(client, t0["tag_url"], name="=HYPERLINK(\"http://evil\")")
    csv_text = (await organizer.get(f"/api/events/{ev['id']}/report.csv", params={"include_names": 1})).text
    assert "'=HYPERLINK" in csv_text


async def test_whatsapp_start_opt_in(client, db, monkeypatch):
    import notifications

    sent = []
    monkeypatch.setattr(notifications, "send_whatsapp_background", lambda to, body: sent.append((to, body)))
    admin, _, org = await _setup_org(client, db)
    ev = await _create_event(admin, org["id"], count=3)
    t0 = (await _tag_urls(admin, ev["id"], 1))[0]
    await _claim(client, t0["tag_url"], phone="9876543210")
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "919876543210", "text": {"body": f"START {t0['code']}"}}]}}]}]}
    r = await client.post("/api/webhooks/whatsapp", json=payload)
    assert r.status_code == 200
    guest = await db.guest_owners.find_one({})
    assert guest["whatsapp_opt_in"] and guest["whatsapp_window_opens_at"]
    assert sent and sent[0][0] == "919876543210"
    from owners import alert_profile

    assert alert_profile(guest)["whatsapp_alerts"] is True  # free window open → WhatsApp allowed
    assert alert_profile(guest)["_free_only"] is True  # …but never a paid template
