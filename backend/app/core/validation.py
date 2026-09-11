"""Shared field validation for user-supplied text.

Two failures kept recurring in the API: a name of nothing but spaces passed `min_length` and
produced a row that renders blank everywhere, and a name carrying a NUL byte reached Postgres,
which cannot store it, so the driver raised and the request came back as a 500 instead of a 422.
Both are input problems and belong in one place.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field

# C0 controls other than tab/newline/carriage-return, plus DEL. NUL is the one that reaches the
# database and turns a bad request into a server error; the rest have no business in a name.
_FORBIDDEN = {chr(c) for c in range(0x00, 0x20)} - {"\t", "\n", "\r"} | {chr(0x7F)}


def clean_text(v: str | None) -> str | None:
    """Strip surrounding whitespace and reject control characters.

    Returns the stripped value so callers store what they display. Raises ValueError, which
    Pydantic turns into the API's 422 envelope.
    """
    if v is None:
        return None
    if any(ch in _FORBIDDEN for ch in v):
        raise ValueError("control characters are not allowed")
    out = v.strip()
    if not out:
        raise ValueError("must not be blank")
    return out


def optional_text(v: str | None) -> str | None:
    """`clean_text` for fields where None means "leave unchanged"."""
    return None if v is None else clean_text(v)


# A display name: 1..80 visible characters after stripping.
DisplayName = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(clean_text)]
OptionalDisplayName = Annotated[
    str | None, Field(default=None, max_length=80), AfterValidator(optional_text)
]
