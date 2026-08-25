"""Blog ingest via RSS/Atom feeds."""

from __future__ import annotations

import os
from pathlib import Path

import feedparser
import httpx

from config import ENDPOINTS, FIXTURE_PATHS
from db import init_db
from normalize import rss_entries, write_documents, write_run


def _entry_date(entry) -> str | None:
    for attr in ("published", "updated", "created"):
        if getattr(entry, attr, None):
            return getattr(entry, attr)
    return None


def _parse_feed_text(text: str) -> list[dict]:
    parsed = feedparser.parse(text)
    out = []
    for e in parsed.entries:
        out.append(
            {
                "title": getattr(e, "title", None),
                "url": getattr(e, "link", None),
                "published_at": _entry_date(e),
                "summary": getattr(e, "summary", None) or getattr(e, "description", None),
                "author": getattr(e, "author", None),
            }
        )
    return out


def _load_feed(company: str, live: bool) -> tuple[list[dict], bool, str | None]:
    url = ENDPOINTS[company]["blog_rss"]
    key = f"{company}_blog"
    fixture = FIXTURE_PATHS[key]
    if live:
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        Path(fixture).write_text(resp.text)
        text = resp.text
    else:
        text = Path(fixture).read_text()

    entries = _parse_feed_text(text)
    truncated = False
    note = None
    if company == "hashicorp":
        truncated = True
        note = "RSS feed caps at ~20 items; oldest entry ~2026-06-25"
    return entries, truncated, note


def ingest_blogs(conn, live: bool = False) -> dict[str, int]:
    stats: dict[str, int] = {}
    for company in ("vercel", "supabase", "hashicorp"):
        entries, truncated, note = _load_feed(company, live)
        docs, run = rss_entries(company, entries, truncated=truncated, note=note)
        rid = write_run(conn, run)
        stats[f"{company}_blog"] = write_documents(conn, docs, rid)
    conn.commit()
    return stats


if __name__ == "__main__":
    conn = init_db()
    print(ingest_blogs(conn, live=os.getenv("INGEST_LIVE", "0") == "1"))
