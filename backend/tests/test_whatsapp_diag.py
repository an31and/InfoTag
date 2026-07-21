"""Tests for the WhatsApp diagnostic endpoints (no real network)."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "infotag_test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import notifications
from routes.admin_routes import _require_admin, router as admin_router


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[_require_admin] = lambda: {"id": "u1", "role": "admin"}
    return TestClient(app)


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class TestHealth:
    def test_health_reports_config_and_probe(self, client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_TOKEN", "EAAtoken")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
        import requests
        monkeypatch.setattr(
            requests, "get",
            lambda *a, **k: _Resp(200, {"display_phone_number": "+91 90000 00000", "verified_name": "Info-Tag"}),
        )
        r = client.get("/api/admin/whatsapp/health")
        assert r.status_code == 200
        body = r.json()
        assert body["config"]["token_set"] is True
        assert body["config"]["phone_number_id_set"] is True
        assert body["probe"]["ok"] is True
        assert body["probe"]["response"]["verified_name"] == "Info-Tag"

    def test_health_probe_surfaces_expired_token(self, client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_TOKEN", "EAAexpired")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
        import requests
        err = {"error": {"message": "Error validating access token", "code": 190}}
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(401, err))
        body = client.get("/api/admin/whatsapp/health").json()
        assert body["probe"]["ok"] is False
        assert body["probe"]["response"]["error"]["code"] == 190


class TestSendTest:
    def test_requires_recipient(self, client):
        assert client.post("/api/admin/whatsapp/test", json={}).status_code == 400

    def test_returns_meta_success(self, client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_TOKEN", "EAAtoken")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
        import requests
        monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(200, {"messages": [{"id": "wamid.X"}]}))
        r = client.post("/api/admin/whatsapp/test", json={"to": "+919876543210"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_surfaces_24h_window_error(self, client, monkeypatch):
        monkeypatch.setenv("WHATSAPP_TOKEN", "EAAtoken")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
        import requests
        err = {"error": {"message": "Re-engagement message", "code": 131047}}
        monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(400, err))
        body = client.post("/api/admin/whatsapp/test", json={"to": "+919876543210"}).json()
        assert body["ok"] is False
        assert body["response"]["error"]["code"] == 131047

    def test_not_configured(self, client, monkeypatch):
        monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_API_KEY", raising=False)
        monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
        body = client.post("/api/admin/whatsapp/test", json={"to": "+919876543210"}).json()
        assert body["ok"] is False
        assert "configured" in body["reason"].lower()
