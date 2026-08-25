#!/usr/bin/env python3
"""Build data.db from committed fixtures — no network required."""

from __future__ import annotations

import os
from pathlib import Path

from db import DB_PATH, init_db, rebuild_fts
from ingest_blogs import ingest_blogs
from ingest_github import ingest_github
from ingest_jobs_api import ingest_jobs
from normalize import hashicorp_jobs_excluded, write_run


def seed_hashicorp_jobs(conn) -> None:
    note = (
        "careers redirects to ibm.com/careers/search?q=hashicorp; "
        "3 hits are IBM Consulting roles matching the string, not HashiCorp postings — excluded deliberately"
    )
    run = hashicorp_jobs_excluded(note)
    write_run(conn, run)
    conn.commit()


def main() -> None:
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    conn = init_db()
    live = os.getenv("INGEST_LIVE", "0") == "1"
    print("ingest jobs", ingest_jobs(conn, live=live))
    print("ingest blogs", ingest_blogs(conn, live=live))
    print("ingest github", ingest_github(conn, live=live))
    seed_hashicorp_jobs(conn)
    rebuild_fts(conn)

    counts = conn.execute(
        "SELECT source_type, COUNT(*) c FROM documents GROUP BY source_type"
    ).fetchall()
    jobs = conn.execute("SELECT COUNT(*) FROM documents WHERE source_type='job'").fetchone()[0]
    print("job rows", jobs)
    print("by source", {r[0]: r[1] for r in counts})


if __name__ == "__main__":
    main()
