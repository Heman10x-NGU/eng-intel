"""Temporal cue detection and relative window parsing (ported from palimp/temporal.py)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional


def detect_temporal_cues(query: str) -> Optional[str]:
    q = query.lower()
    historical_cues = [
        "before",
        "previous",
        "formerly",
        "in 2022",
        "in 2023",
        "in 2024",
        "in 2025",
        "last year",
        "used to",
        "was",
        "were",
        "had been",
    ]
    current_cues = ["now", "currently", "today", "right now", "at present"]

    for cue in historical_cues:
        if cue in q:
            return "historical"
    for cue in current_cues:
        if cue in q:
            return "current"
    return None


def _parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_relative_window(query: str, ref: date | None = None) -> tuple[date | None, date | None]:
    """Parse phrases like 'last 30 days' or 'last 6 months' into since/until."""
    ref_dt = datetime.combine(ref or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    q = query.lower()
    until = ref_dt.date()

    m = re.search(r"last\s+(\d+)\s+days?", q)
    if m:
        days = int(m.group(1))
        return until - timedelta(days=days), until

    m = re.search(r"last\s+(\d+)\s+months?", q)
    if m:
        months = int(m.group(1))
        return until - timedelta(days=months * 30), until

    m = re.search(r"last\s+(\d+)\s+weeks?", q)
    if m:
        weeks = int(m.group(1))
        return until - timedelta(weeks=weeks), until

    if "last 6 months" in q or "past 6 months" in q or "6 months" in q:
        return until - timedelta(days=180), until

    if "last 30 days" in q or "past 30 days" in q or "last month" in q:
        return until - timedelta(days=30), until

    return None, None
