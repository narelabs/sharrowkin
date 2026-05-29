"""Session-aware logging context for Sharrowkin.

Provides a ContextVar-based session_id that is automatically injected
into every log record, so a single WebSocket request's logs can be
filtered with `grep "sid=<uuid>" backend.log`.

Usage:
    from core.logging_ctx import set_session_id, setup_logging
    setup_logging()  # call once at startup
    set_session_id("session_abc123")  # at the start of a request
    logger.info("Doing work")  # produces "... [sid=session_abc123] Doing work"
"""

from __future__ import annotations

import contextvars
import logging
import sys

_session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "sharrowkin_session_id", default="-"
)


def set_session_id(session_id: str) -> contextvars.Token:
    """Set the current session_id. Returns a token that can be used to reset."""
    return _session_id_var.set(session_id)


def get_session_id() -> str:
    return _session_id_var.get()


def reset_session_id(token: contextvars.Token) -> None:
    _session_id_var.reset(token)


class _SessionIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = _session_id_var.get()
        return True


_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s [sid=%(session_id)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger. Safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on hot reload
    for h in list(root.handlers):
        if getattr(h, "_sharrowkin_session_handler", False):
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
    handler.addFilter(_SessionIdFilter())
    handler._sharrowkin_session_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    # Quiet down noisy libraries
    for noisy in ("httpx", "httpcore", "watchfiles", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
