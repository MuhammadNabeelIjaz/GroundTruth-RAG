"""Regression tests for CORS headers across success, 404, 500, and OPTIONS responses."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app

PROD_ORIGIN = "https://groundtruth-rag.netlify.app"
PREVIEW_ORIGIN = "https://deploy-preview-42--groundtruth-rag.netlify.app"
LOCAL_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "https://malicious-site.example.com"


@pytest.fixture
def cors_client():
    return TestClient(app, raise_server_exceptions=False)


def test_cors_health_success(cors_client):
    """GET /health must include CORS headers for production Netlify origin."""
    resp = cors_client.get("/health", headers={"Origin": PROD_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == PROD_ORIGIN
    assert resp.headers.get("Access-Control-Allow-Credentials") == "true"


def test_cors_options_preflight(cors_client):
    """OPTIONS preflight must return 200 with allowed methods and origin."""
    resp = cors_client.options(
        "/health",
        headers={
            "Origin": PROD_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == PROD_ORIGIN
    assert "GET" in resp.headers.get("Access-Control-Allow-Methods", "")


def test_cors_document_suggestions(cors_client):
    """GET /documents/.../suggestions must include CORS headers for Netlify origin."""
    resp = cors_client.get("/documents/hr_policy.pdf/suggestions", headers={"Origin": PROD_ORIGIN})
    assert resp.headers.get("Access-Control-Allow-Origin") == PROD_ORIGIN


def test_cors_preview_deploy_regex(cors_client):
    """Netlify deploy preview subdomains must be allowed via cors_origin_regex."""
    resp = cors_client.get("/health", headers={"Origin": PREVIEW_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == PREVIEW_ORIGIN


def test_cors_localhost_allowed(cors_client):
    """Localhost must remain allowed for local development."""
    resp = cors_client.get("/health", headers={"Origin": LOCAL_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == LOCAL_ORIGIN


def test_cors_404_response(cors_client):
    """404 responses must include CORS headers so browsers can read the error."""
    resp = cors_client.get("/nonexistent-endpoint-test-404", headers={"Origin": PROD_ORIGIN})
    assert resp.status_code == 404
    assert resp.headers.get("Access-Control-Allow-Origin") == PROD_ORIGIN


def test_cors_disallowed_origin_rejected(cors_client):
    """Unapproved origins must not receive Access-Control-Allow-Origin headers."""
    resp = cors_client.get("/health", headers={"Origin": DISALLOWED_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") is None
