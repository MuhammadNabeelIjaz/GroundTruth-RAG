import logging

import pytest

from backend.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_backend_logger():
    """Leave the shared "backend" logger as we found it."""
    logger = logging.getLogger("backend")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    yield
    logger.handlers[:] = saved_handlers
    logger.setLevel(saved_level)


def test_level_is_applied_case_insensitively():
    configure_logging("debug")

    assert logging.getLogger("backend").level == logging.DEBUG


def test_calling_twice_does_not_add_a_second_handler():
    logger = logging.getLogger("backend")

    configure_logging("INFO")
    handlers_after_first_call = len(logger.handlers)
    configure_logging("INFO")

    assert len(logger.handlers) == handlers_after_first_call


def test_invalid_level_raises_a_clear_error():
    with pytest.raises(ValueError, match="Invalid log level"):
        configure_logging("LOUD")
