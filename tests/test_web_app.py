"""End-to-end-ish tests for the FastAPI surface, exercised offline.

These run entirely against the `mock` vision backend (no network, no GPU) and
isolate all on-disk state (sessions, submissions DB) into a tmp dir via env
vars so they don't touch the developer's real ~/.shemesh-ops data.

Focus areas:
  * security: path-traversal rejection on the /{sid} routes, no traceback
    leakage on unhandled errors;
  * upload validation: type sniffing, magic-byte spoofing, size cap;
  * the happy-path multi-step flow with the mock backend.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Force the offline mock backend; never reach out to ollama/openai.
    monkeypatch.setenv("SHEMESH_VISION", "mock")
    monkeypatch.delenv("SHEMESH_DEBUG", raising=False)

    # Isolate persistent state by retargeting the module-level singletons at a
    # tmp dir (avoids importlib.reload, which is brittle and order-dependent).
    import sys

    import shemesh_ops.web.sessions as sessions_mod
    import shemesh_ops.storage as storage_mod
    # NOTE: `shemesh_ops.web.__init__` does `from .app import app`, which makes
    # the attribute `shemesh_ops.web.app` resolve to the FastAPI *instance*, not
    # the submodule. Pull the actual module object out of sys.modules instead.
    import shemesh_ops.web.app  # noqa: F401 (ensures it's imported)
    app_mod = sys.modules["shemesh_ops.web.app"]

    session_root = (tmp_path / "sessions").resolve()
    session_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sessions_mod, "SESSION_ROOT", session_root)
    fresh_store = sessions_mod.SessionStore()
    monkeypatch.setattr(sessions_mod, "store", fresh_store)
    # app.py imported the store by value (`from .sessions import store as
    # session_store`), so patch that binding on the module object directly.
    # (Can't use monkeypatch's dotted-path form here — `shemesh_ops.web.app`
    # resolves to the FastAPI instance, not the module, due to the __init__
    # re-export collision noted above.)
    monkeypatch.setattr(app_mod, "session_store", fresh_store)

    monkeypatch.setattr(storage_mod, "DEFAULT_DB_PATH", tmp_path / "subs.db")

    fastapi_app = app_mod.app
    return TestClient(fastapi_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Security: path traversal on the /{sid} routes


# NOTE: literal "../" segments are collapsed client-side by httpx before the
# request is sent, so they never reach the server and can't be asserted on
# here. We test the cases that DO reach the route: percent-encoded traversal
# and malformed-but-single-segment tokens. The unit test
# `test_session_id_validator_is_strict` covers the "../" shape directly.
@pytest.mark.parametrize("evil", [
    "%2e%2e",                # percent-encoded ".."
    "%2e%2e%2fetc",          # percent-encoded "../etc"
    "ZZZZZZZZZZZZ",          # right length, not hex
    "abc",                   # too short
    "0123456789abcdef0123",  # too long
    "0123456789ab.pdf",      # trailing junk
])
def test_review_route_rejects_bad_session_ids(client, evil):
    r = client.get(f"/review/{evil}")
    # Never a 200 (would mean the traversal/garbage was accepted) or 500.
    assert r.status_code == 404


def test_session_id_validator_is_strict():
    from shemesh_ops.web.sessions import is_valid_session_id
    assert is_valid_session_id("0123456789ab")
    assert not is_valid_session_id("..")
    assert not is_valid_session_id("0123456789AB")  # uppercase not minted
    assert not is_valid_session_id("0123456789ab/")
    assert not is_valid_session_id("")


# ---------------------------------------------------------------------------
# Security: unhandled errors must not leak tracebacks to the page


def test_unhandled_error_hides_traceback_by_default(client):
    import sys
    app_mod = sys.modules["shemesh_ops.web.app"]

    @app_mod.app.get("/_boom")
    async def _boom():  # pragma: no cover - exercised via the request below
        raise RuntimeError("secret path /home/secret/x.key leaked here")

    r = client.get("/_boom")
    assert r.status_code == 500
    assert "Traceback" not in r.text
    assert "secret path" not in r.text  # raw exception message not shown


# ---------------------------------------------------------------------------
# Health probe


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["vision_backend"] == "mock"
    assert "active_sessions" in body


# ---------------------------------------------------------------------------
# Upload validation


def _img(data=b"\xff\xd8\xff\xe0fakejpeg"):
    return io.BytesIO(data)


def test_upload_rejects_wrong_content_type(client):
    # id_front declared as image but sent as text/plain -> 400.
    files = {
        "id_front": ("id.txt", io.BytesIO(b"hello"), "text/plain"),
        "id_back": ("b.jpg", _img(), "image/jpeg"),
        "bank": ("bank.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
        "tagmulim": ("t.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
        "pitsuyim": ("p.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
    }
    r = client.post("/upload", files=files)
    assert r.status_code == 400


def test_upload_rejects_pdf_with_spoofed_magic_bytes(client):
    # Correct content-type + .pdf extension, but the bytes are not a PDF.
    files = {
        "id_front": ("f.jpg", _img(), "image/jpeg"),
        "id_back": ("b.jpg", _img(), "image/jpeg"),
        "bank": ("bank.pdf", io.BytesIO(b"<html>not a pdf</html>"), "application/pdf"),
        "tagmulim": ("t.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
        "pitsuyim": ("p.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
    }
    r = client.post("/upload", files=files)
    assert r.status_code == 400
    assert "PDF" in r.text


def test_upload_enforces_size_cap(client, monkeypatch):
    import sys
    app_mod = sys.modules["shemesh_ops.web.app"]
    monkeypatch.setattr(app_mod, "MAX_UPLOAD_BYTES", 1024)  # 1 KB cap
    big = b"%PDF-1.4 " + b"0" * 4096
    files = {
        "id_front": ("f.jpg", _img(), "image/jpeg"),
        "id_back": ("b.jpg", _img(), "image/jpeg"),
        "bank": ("bank.pdf", io.BytesIO(big), "application/pdf"),
        "tagmulim": ("t.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
        "pitsuyim": ("p.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"),
    }
    r = client.post("/upload", files=files)
    assert r.status_code == 413
