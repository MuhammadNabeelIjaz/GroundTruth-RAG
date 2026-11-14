from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    # Compare with the app's own settings, not hard-coded strings: a developer's
    # personal .env (e.g. APP_NAME=my-app) must not break this test. The
    # default values themselves are checked in test_config.py.
    assert response.json() == {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }
