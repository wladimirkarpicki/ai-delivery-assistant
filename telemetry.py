"""
Central logging configuration.

Before this existed the app emitted warnings through four unrelated
`logging.getLogger` calls and relied on Python's defaults, which means:

- no format, so a production line carried no timestamp, level or logger
  name and could not be correlated with anything;
- no level, so uvicorn's default WARNING hid the detail that makes a
  failure diagnosable;
- no request identity, so a single failing meeting request looked
  identical to the four before it.

The logger names are namespaced under ai-delivery-assistant so one
configuration covers the application, and the handler is attached to the
root as well so uvicorn's own loggers keep working.

A request id is generated per HTTP request and echoed on the response,
which is what lets a user-reported failure be found in the log. It is a
per-process identifier, not a distributed trace id: the app has no
tracing backend, and inventing one would be decoration.
"""

import logging
import os
import sys
import uuid

LOGGER_NAME = "ai-delivery-assistant"
REQUEST_ID_HEADER = "X-Request-ID"

_CONFIGURED = False


def configure_logging() -> None:
    """
    Attach the application's formatter and level to the root logger.

    Idempotent: create_app() runs this once and the test suite calls it
    per app, so a second call must not stack handlers.
    """
    global _CONFIGURED

    if _CONFIGURED:
        return

    root = logging.getLogger()

    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        root.addHandler(handler)

    level = (os.getenv("LOG_LEVEL") or "INFO").upper()

    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        level = "INFO"

    root.setLevel(level)
    logging.getLogger(LOGGER_NAME).setLevel(level)

    _CONFIGURED = True


def new_request_id() -> str:
    """A short per-request identifier for log correlation."""
    return uuid.uuid4().hex[:12]
