import io

import pytest

import app as app_module
from legaldebunkr import pipeline


@pytest.fixture()
def client():
    app_module.limiter.reset()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _upload(client, name, content):
    return client.post("/api/analyze", data={"file": (io.BytesIO(content), name)},
                       content_type="multipart/form-data")


def test_rejects_bad_extension(client):
    assert _upload(client, "x.exe", b"MZ").status_code == 400


def test_rejects_mismatched_signature(client):
    r = _upload(client, "fake.pdf", b"not really a pdf")
    assert r.status_code == 400
    assert "match" in r.get_json()["error"]


def test_analyze_is_rate_limited(client):
    codes = [_upload(client, "x.exe", b"MZ").status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400]
    assert codes[3] == 429


def test_ask_is_rate_limited_and_validates(client):
    assert client.post("/api/ask", json={"doc_id": "nope", "question": "hi"}).status_code == 404
    for _ in range(2):
        client.post("/api/ask", json={})
    assert client.post("/api/ask", json={}).status_code == 429


def test_question_length_cap(client, monkeypatch):
    monkeypatch.setattr(pipeline, "get_analysis", lambda _id: {"sections": [], "fields": {}})
    r = client.post("/api/ask", json={"doc_id": "x", "question": "a" * 600})
    assert r.status_code == 400


def test_health_exposes_no_secrets(client):
    body = client.get("/health").get_json()
    assert set(body.values()) <= {True, False}


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_store_expires(monkeypatch):
    pipeline._put("abc", {"x": 1})
    assert pipeline.get_analysis("abc") == {"x": 1}
    pipeline._STORE["abc"] = (0.0, {"x": 1})  # stamped long ago
    assert pipeline.get_analysis("abc") is None
