"""GitHub org events ingest."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from config import ENDPOINTS, FIXTURE_PATHS
from db import init_db
from normalize import github_activity, write_documents, write_run


def _load_events(company: str, live: bool) -> list[dict]:
    org = ENDPOINTS[company]["github_org"]
    fixture = FIXTURE_PATHS[f"github_{company}"]
    if live:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "eng-intel"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = f"https://api.github.com/orgs/{org}/events?per_page=100"
        resp = httpx.get(url, headers=headers, timeout=60.0)
        if resp.status_code == 403:
            return json.loads(Path(fixture).read_text())
        resp.raise_for_status()
        data = resp.json()
        Path(fixture).write_text(json.dumps(data))
        return data
    return json.loads(Path(fixture).read_text())


def ingest_github(conn, live: bool = False) -> dict[str, int]:
    stats: dict[str, int] = {}
    for company in ("vercel", "supabase", "hashicorp"):
        events = _load_events(company, live)
        docs, run = github_activity(company, events)
        rid = write_run(conn, run)
        stats[f"{company}_github"] = write_documents(conn, docs, rid)
    conn.commit()
    return stats


if __name__ == "__main__":
    conn = init_db()
    print(ingest_github(conn, live=os.getenv("INGEST_LIVE", "0") == "1"))
