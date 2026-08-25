"""Normalize any source payload into document + ingest_run rows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any

from bs4 import BeautifulSoup


@dataclass
class IngestRun:
    company: str
    source_type: str
    method: str
    fetched_at: str
    n_rows: int
    coverage_start: str | None
    coverage_end: str | None
    truncated: int = 0
    note: str | None = None


@dataclass
class Document:
    company: str
    source_type: str
    title: str | None
    url: str
    published_at: str | None
    body_text: str | None
    extra_json: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return unescape(text)


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (ValueError, TypeError):
        return None


def derive_is_remote(location: str | None, raw_remote: Any = None) -> bool | None:
    if raw_remote is True:
        return True
    if raw_remote is False:
        return False
    if not location:
        return None
    loc = location.lower()
    if re.search(r"\bremote\b", loc):
        return True
    if re.search(r"\b(hybrid|on-?site|office)\b", loc):
        return False
    return None


def greenhouse_jobs(company: str, payload: dict) -> tuple[list[Document], IngestRun]:
    docs: list[Document] = []
    dates: list[str] = []
    for job in payload.get("jobs", []):
        loc = (job.get("location") or {}).get("name")
        dept = None
        if job.get("departments"):
            dept = job["departments"][0].get("name")
        pub = _parse_date(job.get("first_published") or job.get("updated_at"))
        if pub:
            dates.append(pub)
        body = _strip_html(job.get("content"))
        docs.append(
            Document(
                company=company,
                source_type="job",
                title=job.get("title"),
                url=job.get("absolute_url") or job.get("internal_job_id", ""),
                published_at=pub,
                body_text=body,
                extra_json={
                    "department": dept,
                    "location": loc,
                    "is_remote": derive_is_remote(loc),
                    "source": "greenhouse",
                },
            )
        )
    dates_sorted = sorted(dates) if dates else []
    run = IngestRun(
        company=company,
        source_type="job",
        method="api",
        fetched_at=_now_iso(),
        n_rows=len(docs),
        coverage_start=dates_sorted[0] if dates_sorted else None,
        coverage_end=dates_sorted[-1] if dates_sorted else None,
        truncated=0,
        note=None,
    )
    return docs, run


def ashby_jobs(company: str, payload: dict) -> tuple[list[Document], IngestRun]:
    docs: list[Document] = []
    dates: list[str] = []
    for job in payload.get("jobs", []):
        loc = job.get("location")
        pub = _parse_date(job.get("publishedAt"))
        if pub:
            dates.append(pub)
        body = job.get("descriptionPlain") or _strip_html(job.get("descriptionHtml"))
        docs.append(
            Document(
                company=company,
                source_type="job",
                title=job.get("title"),
                url=job.get("jobUrl") or "",
                published_at=pub,
                body_text=body,
                extra_json={
                    "department": job.get("department"),
                    "team": job.get("team"),
                    "location": loc,
                    "is_remote": derive_is_remote(loc, job.get("isRemote")),
                    "ashby_is_remote_raw": job.get("isRemote"),
                    "source": "ashby",
                },
            )
        )
    dates_sorted = sorted(dates) if dates else []
    run = IngestRun(
        company=company,
        source_type="job",
        method="api",
        fetched_at=_now_iso(),
        n_rows=len(docs),
        coverage_start=dates_sorted[0] if dates_sorted else None,
        coverage_end=dates_sorted[-1] if dates_sorted else None,
        truncated=0,
        note="Ashby isRemote null on all rows; remote derived from location string",
    )
    return docs, run


def rss_entries(company: str, entries: list[dict], truncated: bool = False, note: str | None = None) -> tuple[list[Document], IngestRun]:
    docs: list[Document] = []
    dates: list[str] = []
    for entry in entries:
        pub = _parse_date(entry.get("published_at"))
        if pub:
            dates.append(pub)
        body = entry.get("summary") or entry.get("body") or ""
        docs.append(
            Document(
                company=company,
                source_type="blog",
                title=entry.get("title"),
                url=entry.get("url") or "",
                published_at=pub,
                body_text=body,
                extra_json={"source": "rss", "author": entry.get("author")},
            )
        )
    dates_sorted = sorted(dates) if dates else []
    run = IngestRun(
        company=company,
        source_type="blog",
        method="rss",
        fetched_at=_now_iso(),
        n_rows=len(docs),
        coverage_start=dates_sorted[0] if dates_sorted else None,
        coverage_end=dates_sorted[-1] if dates_sorted else None,
        truncated=1 if truncated else 0,
        note=note,
    )
    return docs, run


def github_activity(company: str, events: list[dict], window_days: int = 7) -> tuple[list[Document], IngestRun]:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    counts = {"push": 0, "pr": 0, "issues": 0, "repos": set(), "authors": set()}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        created = _parse_date(ev.get("created_at"))
        if not created:
            continue
        if datetime.fromisoformat(created) < cutoff:
            continue
        etype = ev.get("type", "")
        if etype == "PushEvent":
            counts["push"] += 1
        elif etype == "PullRequestEvent":
            counts["pr"] += 1
        elif etype == "IssuesEvent":
            counts["issues"] += 1
        repo = (ev.get("repo") or {}).get("name")
        if repo:
            counts["repos"].add(repo)
        actor = (ev.get("actor") or {}).get("login")
        if actor:
            counts["authors"].add(actor)

    events_7d = counts["push"] + counts["pr"]
    extra = {
        "events_7d": events_7d,
        "push_events": counts["push"],
        "pr_events": counts["pr"],
        "issues_events": counts["issues"],
        "distinct_repos": len(counts["repos"]),
        "distinct_authors": len(counts["authors"]),
        "window_days": window_days,
        "source": "github",
    }
    doc = Document(
        company=company,
        source_type="repo_activity",
        title=f"{company} GitHub activity ({window_days}d)",
        url=f"https://github.com/{company}",
        published_at=now.replace(microsecond=0).isoformat(),
        body_text=json.dumps(extra),
        extra_json=extra,
    )
    run = IngestRun(
        company=company,
        source_type="repo_activity",
        method="api",
        fetched_at=_now_iso(),
        n_rows=1,
        coverage_start=cutoff.replace(microsecond=0).isoformat(),
        coverage_end=now.replace(microsecond=0).isoformat(),
        truncated=0,
        note=f"Push+PR events over {window_days} days from org events API (first page)",
    )
    return [doc], run


def hashicorp_jobs_excluded(run_note: str) -> IngestRun:
    return IngestRun(
        company="hashicorp",
        source_type="job",
        method="cloak",
        fetched_at=_now_iso(),
        n_rows=0,
        coverage_start=None,
        coverage_end=None,
        truncated=1,
        note=run_note,
    )


def write_run(conn, run: IngestRun) -> int:
    cur = conn.execute(
        """
        INSERT INTO ingest_runs (company, source_type, method, fetched_at, n_rows,
                                 coverage_start, coverage_end, truncated, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.company,
            run.source_type,
            run.method,
            run.fetched_at,
            run.n_rows,
            run.coverage_start,
            run.coverage_end,
            run.truncated,
            run.note,
        ),
    )
    return int(cur.lastrowid)


def write_documents(conn, docs: list[Document], ingest_run_id: int) -> int:
    n = 0
    for doc in docs:
        conn.execute(
            """
            INSERT INTO documents (company, source_type, title, url, published_at, body_text, extra_json, ingest_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              title=excluded.title,
              published_at=excluded.published_at,
              body_text=excluded.body_text,
              extra_json=excluded.extra_json,
              ingest_run_id=excluded.ingest_run_id
            """,
            (
                doc.company,
                doc.source_type,
                doc.title,
                doc.url,
                doc.published_at,
                doc.body_text,
                json.dumps(doc.extra_json),
                ingest_run_id,
            ),
        )
        n += 1
    return n
