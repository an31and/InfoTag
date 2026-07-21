"""In-process tests for the landing-section settings API (mongomock, no services)."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "infotag_test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import db as db_module
from routes.admin_routes import LANDING_SECTIONS, _require_admin, router as admin_router
from routes.public_routes import router as public_router


@pytest.fixture()
def app_client(monkeypatch):
    mock_db = AsyncMongoMockClient()["infotag_test"]
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    import routes.admin_routes as ar
    import routes.public_routes as pr
    monkeypatch.setattr(ar, "get_db", lambda: mock_db)
    monkeypatch.setattr(pr, "get_db", lambda: mock_db)

    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(public_router)
    app.dependency_overrides[_require_admin] = lambda: {"id": "u1", "role": "admin"}
    return TestClient(app), mock_db


class TestSettings:
    def test_defaults_all_on(self, app_client):
        client, _ = app_client
        r = client.get("/api/admin/settings")
        assert r.status_code == 200
        flags = r.json()["landing_sections"]
        assert set(flags) == set(LANDING_SECTIONS)
        assert all(flags.values())

    def test_patch_persists_and_public_endpoint_reflects_it(self, app_client):
        client, _ = app_client
        r = client.patch("/api/admin/settings", json={"landing_sections": {"videos": False, "faq": False}})
        assert r.status_code == 200
        assert r.json()["landing_sections"]["videos"] is False

        pub = client.get("/api/public/site-settings").json()["landing_sections"]
        assert pub["videos"] is False
        assert pub["faq"] is False
        assert pub["how"] is True  # untouched sections stay on

    def test_patch_ignores_unknown_keys(self, app_client):
        client, _ = app_client
        r = client.patch("/api/admin/settings", json={"landing_sections": {"hack": True}})
        assert r.status_code == 400

    def test_patch_empty_payload_rejected(self, app_client):
        client, _ = app_client
        assert client.patch("/api/admin/settings", json={}).status_code == 400
