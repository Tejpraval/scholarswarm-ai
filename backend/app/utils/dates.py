"""Date parsing helpers for safely deciding whether verified deadlines are current."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


_FORMATS = (
    "%Y-%m-%d",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
)


def parse_deadline(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    candidate = value.strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def deadline_is_current(value: Optional[str], *, today: Optional[date] = None) -> Optional[bool]:
    """Return None when no exact date is parseable, otherwise whether it is not expired."""
    parsed = parse_deadline(value)
    if parsed is None:
        return None
    return parsed >= (today or date.today())
