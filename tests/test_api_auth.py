"""The shared-secret gate in sentinel/api/auth.py, and the CORS allowlist.

TestClient is deliberately not used as a context manager: that would run the
app's startup hook and reconnect the repo, undoing the tmp-path database the
autouse `fresh_db` fixture has already installed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel import config
from sentinel.api.main import app
from sentinel.graph.transport import _auth_headers

TOKEN = "test-token-value"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def gated(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_TOKEN", TOKEN)


# ------------------------------------------------------------------ gate ---
def test_open_when_no_token_configured(client, monkeypatch):
    """Unset is the local-dev default and must leave the API reachable."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    assert client.get("/health").status_code == 200


def test_rejects_missing_token(client, gated):
    r = client.get("/health")
    assert r.status_code == 401
    assert "token" in r.json()["detail"]


def test_rejects_wrong_token(client, gated):
    r = client.get("/health", headers={"X-Sentinel-Token": "not-it"})
    assert r.status_code == 401


def test_rejects_token_that_is_a_prefix(client, gated):
    """Guards against a truncating comparison ever creeping in."""
    r = client.get("/health", headers={"X-Sentinel-Token": TOKEN[:-1]})
    assert r.status_code == 401


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": {"X-Sentinel-Token": TOKEN}},
        {"headers": {"Authorization": f"Bearer {TOKEN}"}},
        # The EventSource path: /runs/{id}/events cannot carry a header.
        {"params": {"token": TOKEN}},
    ],
    ids=["header", "bearer", "query"],
)
def test_accepts_every_channel(client, gated, kwargs):
    assert client.get("/health", **kwargs).status_code == 200


def test_non_ascii_token_is_rejected_not_crashed(client, gated):
    """compare_digest raises TypeError on non-ASCII str operands; the presented
    value is attacker-controlled, so this must be a 401 and not a 500."""
    r = client.get("/health", params={"token": "tökén"})
    assert r.status_code == 401


# ---------------------------------------------------------------- public ---
def test_healthz_is_public(client, gated):
    """A load balancer probe has nowhere to hold a secret."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_healthz_discloses_nothing_beyond_liveness(client, monkeypatch):
    """/health reports models, caps and key presence. /healthz must not."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    assert set(client.get("/healthz").json()) == {"ok"}
    assert "api_key_present" in client.get("/health").json()


def test_preflight_passes_without_token(client, gated):
    """A CORS preflight carries no custom headers by definition. Rejecting it
    would stop the browser sending the authenticated request behind it, and the
    failure would surface as an opaque CORS error rather than a 401."""
    r = client.options(
        "/runs",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code == 200


def test_401_still_carries_cors_headers(client, gated):
    """CORS is added after the gate so it wraps it. Were the order reversed the
    401 would unwind without these, and the browser would report a cross-origin
    failure instead of the real reason."""
    r = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


# ------------------------------------------------------------------ cors ---
def test_cors_origins_defaults_to_local_console(monkeypatch):
    monkeypatch.delenv("SENTINEL_CORS_ORIGINS", raising=False)
    assert config.cors_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_parses_and_normalises(monkeypatch):
    monkeypatch.setenv(
        "SENTINEL_CORS_ORIGINS", " https://a.example.com/ , https://b.example.com "
    )
    assert config.cors_origins() == ["https://a.example.com", "https://b.example.com"]


# ------------------------------------------------------- target transport ---
def test_token_sent_to_loopback_target(monkeypatch):
    """The built-in targets are served by this same app, so with the gate on the
    harness has to authenticate to itself."""
    monkeypatch.setenv("SENTINEL_API_TOKEN", TOKEN)
    for endpoint in (
        "http://127.0.0.1:8000/targets/support_bot/chat",
        "http://localhost:8000/targets/support_bot/chat",
        "http://[::1]:8000/targets/support_bot/chat",
    ):
        assert _auth_headers(endpoint) == {"X-Sentinel-Token": TOKEN}


def test_token_never_sent_to_a_third_party_target(monkeypatch):
    """target_endpoint is operator-supplied and may name an agent we are
    attacking. Sending our own API token there would hand that host the key to
    the auditor."""
    monkeypatch.setenv("SENTINEL_API_TOKEN", TOKEN)
    for endpoint in (
        "https://someone-elses-agent.example.com/chat",
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1.evil.example.com/chat",
    ):
        assert _auth_headers(endpoint) == {}


def test_no_headers_when_gate_is_off(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    assert _auth_headers("http://127.0.0.1:8000/targets/support_bot/chat") == {}
