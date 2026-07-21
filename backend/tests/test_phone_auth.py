"""In-process tests for phone-first signup / login (mongomock, no services)."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "infotag_test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

import db as db_module


@pytest.fixture()
def client(monkeypatch):
    mock_db = AsyncMongoMockClient()["infotag_test"]
    monkeypatch.setattr(db_module, "get_db", lambda: mock_db)
    import routes.auth_routes as ar
    monkeypatch.setattr(ar, "get_db", lambda: mock_db)

    app = FastAPI()
    app.include_router(ar.router)
    return TestClient(app)


class TestPhoneSignup:
    def test_signup_with_phone_only_no_email(self, client):
        r = client.post("/api/auth/register", json={"phone": "+91 98765 43210", "password": "supersecret"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] is None
        assert body["phone"] == "+919876543210"
        assert body["display_name"] == "User 3210"

    def test_signup_with_phone_and_email(self, client):
        r = client.post(
            "/api/auth/register",
            json={"phone": "9000000001", "email": "A@B.com", "password": "supersecret", "display_name": "Asha"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == "a@b.com"
        assert r.json()["display_name"] == "Asha"

    def test_signup_with_neither_is_rejected(self, client):
        r = client.post("/api/auth/register", json={"password": "supersecret"})
        assert r.status_code == 422  # pydantic validator

    def test_short_password_rejected(self, client):
        r = client.post("/api/auth/register", json={"phone": "9000000002", "password": "short"})
        assert r.status_code == 422

    def test_duplicate_phone_rejected(self, client):
        client.post("/api/auth/register", json={"phone": "9000000003", "password": "supersecret"})
        r = client.post("/api/auth/register", json={"phone": "+91 90000 00003", "password": "otherpass1"})
        assert r.status_code == 400
        assert "already registered" in r.json()["detail"].lower()

    def test_email_only_still_works(self, client):
        r = client.post("/api/auth/register", json={"email": "solo@x.com", "password": "supersecret"})
        assert r.status_code == 200
        assert r.json()["phone"] == ""


class TestPhoneLogin:
    def _signup(self, client, **kw):
        return client.post("/api/auth/register", json={"password": "supersecret", **kw})

    def test_login_by_phone_various_formats(self, client):
        self._signup(client, phone="+91 98765 43210")
        # login with a differently-formatted version of the same number
        for form in ("9876543210", "+919876543210", "091-98765-43210"):
            r = client.post("/api/auth/login", json={"identifier": form, "password": "supersecret"})
            assert r.status_code == 200, f"{form}: {r.text}"
            assert r.json()["phone"] == "+919876543210"

    def test_login_by_email(self, client):
        self._signup(client, email="me@x.com")
        r = client.post("/api/auth/login", json={"identifier": "ME@x.com", "password": "supersecret"})
        assert r.status_code == 200

    def test_legacy_email_field_login(self, client):
        self._signup(client, email="legacy@x.com")
        r = client.post("/api/auth/login", json={"email": "legacy@x.com", "password": "supersecret"})
        assert r.status_code == 200

    def test_wrong_password_rejected(self, client):
        self._signup(client, phone="9111111111")
        r = client.post("/api/auth/login", json={"identifier": "9111111111", "password": "wrongpass1"})
        assert r.status_code == 401

    def test_unknown_number_rejected(self, client):
        r = client.post("/api/auth/login", json={"identifier": "9999999999", "password": "whatever1"})
        assert r.status_code == 401
