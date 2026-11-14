import logging

from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def test_startup_and_shutdown_are_logged(caplog):
    with caplog.at_level(logging.INFO, logger="backend.main"):
        # Using the client as a context manager runs the startup/shutdown hook.
        with TestClient(app):
            pass

    messages = [record.getMessage() for record in caplog.records]
    assert any(f"Starting {settings.app_name}" in m for m in messages)
    assert any(f"Shutting down {settings.app_name}" in m for m in messages)
