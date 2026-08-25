"""Jobs ingest via Greenhouse and Ashby JSON APIs."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from config import ENDPOINTS, FIXTURE_PATHS
from db import init_db
from normalize import ashby_jobs, greenhouse_jobs, write_documents, write_run


def _load_fixture(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _fetch_or_fixture(url: str, fixture_path: str, live: bool) -> dict:
    if live:
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        Path(fixture_path).write_text(json.dumps(data))
        return data
    return _load_fixture(fixture_path)


def ingest_jobs(conn, live: bool = False) -> dict[str, int]:
    stats: dict[str, int] = {}

    vdata = _fetch_or_fixture(
        ENDPOINTS["vercel"]["jobs_api"],
        FIXTURE_PATHS["vercel_jobs"],
        live,
    )
    vdocs, vrun = greenhouse_jobs("vercel", vdata)
    vid = write_run(conn, vrun)
    stats["vercel_jobs"] = write_documents(conn, vdocs, vid)

    sdata = _fetch_or_fixture(
        ENDPOINTS["supabase"]["jobs_api"],
        FIXTURE_PATHS["supabase_jobs"],
        live,
    )
    sdocs, srun = ashby_jobs("supabase", sdata)
    sid = write_run(conn, srun)
    stats["supabase_jobs"] = write_documents(conn, sdocs, sid)

    conn.commit()
    return stats


if __name__ == "__main__":
    import os

    conn = init_db()
    print(ingest_jobs(conn, live=os.getenv("INGEST_LIVE", "0") == "1"))
