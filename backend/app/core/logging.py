"""Structured logging + X-Request-Id correlation."""
from __future__ import annotations

import logging

_DEF_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once at process start."""
    logging.basicConfig(level=level, format=_DEF_FORMAT)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# Control characters (CR/LF above all) let an attacker-supplied value forge extra log lines.
# Identifiers reaching the logs go through this first: it strips the line structure a forged
# record would need, and caps the length so one field cannot flood a line.
_CTRL = {c: None for c in range(0x20)} | {0x7F: None}


def log_safe(value: object, *, limit: int = 128) -> str:
    """Return ``value`` as a single-line, length-capped string safe to interpolate into a log."""
    text = str(value).translate(_CTRL)
    return text if len(text) <= limit else text[:limit] + "…"
