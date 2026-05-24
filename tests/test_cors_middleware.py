"""Tests for CORSMiddleware — credentialed cross-origin request enforcement (#3623)."""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.api.middleware import CORSMiddleware


# ── Fixtures ──────────────────────────────────────────────────────────────────

ALLOWLIST = ["https://app.example.com", "https://dashboard.example.com"]


async def _data_endpoint(request: Request):
    return PlainTextResponse("ok")


def _make_app(allowlist=None):
    """Return a minimal Starlette app wrapped with CORSMiddleware."""
    routes = [Route("/data", _data_endpoint, methods=["GET", "POST", "OPTIONS"])]
    app = Starlette(routes=routes)
    app.add_middleware(CORSMiddleware, allowlist=allowlist if allowlist is not None else ALLOWLIST)
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app(), raise_server_exceptions=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCORSMiddlewareAllowedOrigin:
    """Requests from origins in the allowlist must succeed with proper headers."""

    def test_get_allowed_origin_returns_200(self, client):
        resp = client.get("/data", headers={"Origin": "https://app.example.com"})
        assert resp.status_code == 200

    def test_allowed_origin_has_acao_header(self, client):
        resp = client.get("/data", headers={"Origin": "https://app.example.com"})
        assert resp.headers["Access-Control-Allow-Origin"] == "https://app.example.com"

    def test_allowed_origin_has_credentials_header(self, client):
        resp = client.get("/data", headers={"Origin": "https://app.example.com"})
        assert resp.headers.get("Access-Control-Allow-Credentials") == "true"

    def test_allowed_origin_has_vary_header(self, client):
        resp = client.get("/data", headers={"Origin": "https://app.example.com"})
        assert "Origin" in resp.headers.get("Vary", "")

    def test_second_allowed_origin_works(self, client):
        resp = client.get("/data", headers={"Origin": "https://dashboard.example.com"})
        assert resp.status_code == 200
        assert resp.headers["Access-Control-Allow-Origin"] == "https://dashboard.example.com"


class TestCORSMiddlewareBlockedOrigin:
    """Requests from origins NOT in the allowlist must be rejected with 403."""

    def test_unknown_origin_returns_403(self, client):
        resp = client.get("/data", headers={"Origin": "https://evil.example.com"})
        assert resp.status_code == 403

    def test_blocked_origin_has_no_acao_header(self, client):
        resp = client.get("/data", headers={"Origin": "https://evil.example.com"})
        assert "Access-Control-Allow-Origin" not in resp.headers

    def test_blocked_origin_still_has_vary_header(self, client):
        resp = client.get("/data", headers={"Origin": "https://evil.example.com"})
        assert "Origin" in resp.headers.get("Vary", "")

    def test_wildcard_origin_is_blocked(self, client):
        """'*' must NEVER be treated as a wildcard match — it is literally compared."""
        resp = client.get("/data", headers={"Origin": "*"})
        assert resp.status_code == 403

    def test_trailing_slash_variant_blocked_for_unlisted_origin(self, client):
        resp = client.get("/data", headers={"Origin": "https://evil.example.com/"})
        assert resp.status_code == 403


class TestCORSMiddlewareTrailingSlashNormalisation:
    """Origin comparison must be normalised (trailing slash stripped)."""

    def test_allowed_origin_with_trailing_slash_is_accepted(self, client):
        # 'https://app.example.com/' should match 'https://app.example.com'
        resp = client.get("/data", headers={"Origin": "https://app.example.com/"})
        assert resp.status_code == 200


class TestCORSMiddlewarePreflight:
    """OPTIONS pre-flight requests must be intercepted and answered directly."""

    def test_preflight_allowed_origin_returns_204(self, client):
        resp = client.options("/data", headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
        })
        assert resp.status_code == 204

    def test_preflight_allowed_origin_has_acao_header(self, client):
        resp = client.options("/data", headers={"Origin": "https://app.example.com"})
        assert resp.headers["Access-Control-Allow-Origin"] == "https://app.example.com"

    def test_preflight_blocked_origin_returns_403(self, client):
        resp = client.options("/data", headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        })
        assert resp.status_code == 403


class TestCORSMiddlewareSameOrigin:
    """Requests without an Origin header are same-origin; they must pass through untouched."""

    def test_no_origin_header_passes_through(self, client):
        resp = client.get("/data")
        assert resp.status_code == 200

    def test_no_origin_header_has_no_cors_headers(self, client):
        resp = client.get("/data")
        assert "Access-Control-Allow-Origin" not in resp.headers


class TestCORSMiddlewareEmptyAllowlist:
    """With an empty allowlist every cross-origin request must be denied."""

    def test_all_origins_blocked_when_allowlist_empty(self):
        app = _make_app(allowlist=[])
        c = TestClient(app, raise_server_exceptions=True)
        resp = c.get("/data", headers={"Origin": "https://app.example.com"})
        assert resp.status_code == 403
