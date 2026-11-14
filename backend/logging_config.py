"""Central logging setup.

All application code logs through `logging.getLogger(__name__)`. Every such
logger lives under the "backend" namespace (e.g. "backend.main"), so one
handler on the "backend" logger is enough to format and print them all.
"""

import logging
import sys

_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_HANDLER_MARKER = "_rag_qa_handler"


def configure_logging(level: str = "INFO") -> None:
    """Set the log level and make sure exactly one console handler exists.

    Safe to call more than once (uvicorn's --reload re-imports the app):
    the level is updated, but no duplicate handler is added.
    Raises ValueError for an unknown level so a typo fails fast and clearly.
    """
    level_name = level.strip().upper()
    if level_name not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Use one of: {', '.join(_VALID_LEVELS)}"
        )

    app_logger = logging.getLogger("backend")
    app_logger.setLevel(level_name)

    if not any(getattr(h, _HANDLER_MARKER, False) for h in app_logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        setattr(handler, _HANDLER_MARKER, True)
        app_logger.addHandler(handler)
