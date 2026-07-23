"""Unit tests for the WhatsApp Cloud API sender.

Exercises the template-vs-free-form logic added so owner alerts reach a
fresh/test number (business-initiated, outside the 24h customer-service
window). Mocks requests.post so no Meta credentials or network are needed.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ["WHATSAPP_TOKEN"] = "test-token"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "123456789012345"

import notifications


class _Resp:
    def __init__(self, status_code=200, text="{}"):
        self.status_code = status_code
        self.text = text


def _capture(monkeypatch, responses):
    """Patch requests.post to record payloads and return queued responses."""
    calls = []
    queue = list(responses)

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return queue.pop(0) if queue else _Resp()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    return calls


def test_free_form_text_when_no_template(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ALERT_TEMPLATE", raising=False)
    calls = _capture(monkeypatch, [_Resp(200)])

    assert notifications.send_whatsapp("+91 89042 23100", "Hello there") is True
    assert len(calls) == 1
    assert calls[0]["type"] == "text"
    assert calls[0]["to"] == "918904223100"  # E.164 without the leading +
    assert calls[0]["text"]["body"] == "Hello there"


def test_template_message_when_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE", "infotag_alert")
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE_LANG", "en_US")
    calls = _capture(monkeypatch, [_Resp(200)])

    ok = notifications.send_whatsapp("918904223100", "Callback request\n\nPhone: 999\n")
    assert ok is True
    assert len(calls) == 1  # template succeeded, no fallback
    tmpl = calls[0]["template"]
    assert calls[0]["type"] == "template"
    assert tmpl["name"] == "infotag_alert"
    assert tmpl["language"]["code"] == "en_US"
    # Multi-line body is collapsed to a single clean line for the {{1}} param.
    param = tmpl["components"][0]["parameters"][0]["text"]
    assert param == "Callback request Phone: 999"
    assert "\n" not in param


def test_template_failure_falls_back_to_text(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALERT_TEMPLATE", "infotag_alert")
    # First call (template) fails, second call (text) succeeds.
    calls = _capture(monkeypatch, [_Resp(400, '{"error":{"code":132001}}'), _Resp(200)])

    assert notifications.send_whatsapp("918904223100", "hi") is True
    assert len(calls) == 2
    assert calls[0]["type"] == "template"
    assert calls[1]["type"] == "text"


def test_skips_when_not_configured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_API_KEY", raising=False)
    calls = _capture(monkeypatch, [_Resp(200)])

    assert notifications.send_whatsapp("918904223100", "hi") is False
    assert calls == []  # no HTTP call attempted
