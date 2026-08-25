"""Coverage window intersection against ingest_runs ledger."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class CoverageResult:
    caveat: str | None
    comparable_since: date | None
    comparable_until: date | None
    gaps: list[dict]
    all_cover: bool


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def check_coverage(
    conn: sqlite3.Connection,
    companies: list[str],
    source_type: str,
    since: date | None,
    until: date | None,
) -> CoverageResult:
    if not companies:
        companies = ["vercel", "supabase", "hashicorp"]

    rows = conn.execute(
        """
        SELECT company, coverage_start, coverage_end, truncated, note, n_rows
        FROM ingest_runs
        WHERE source_type = ?
        ORDER BY fetched_at DESC
        """,
        (source_type,),
    ).fetchall()

    latest: dict[str, sqlite3.Row] = {}
    for row in rows:
        if row["company"] not in latest:
            latest[row["company"]] = row

    gaps = []
    starts: list[date] = []
    ends: list[date] = []

    for company in companies:
        row = latest.get(company)
        if not row:
            gaps.append({"company": company, "reason": "no ingest run recorded"})
            continue
        if row["n_rows"] == 0:
            gaps.append(
                {
                    "company": company,
                    "reason": row["note"] or "zero rows ingested",
                    "truncated": bool(row["truncated"]),
                }
            )
            continue
        cs = _to_date(row["coverage_start"])
        ce = _to_date(row["coverage_end"])
        if cs:
            starts.append(cs)
        if ce:
            ends.append(ce)
        if row["truncated"]:
            gaps.append(
                {
                    "company": company,
                    "reason": row["note"] or "source truncated",
                    "coverage_start": row["coverage_start"],
                    "truncated": True,
                }
            )
        if since and cs and cs > since:
            gaps.append(
                {
                    "company": company,
                    "reason": f"coverage starts {cs.isoformat()}, after requested window",
                    "coverage_start": row["coverage_start"],
                }
            )

    comparable_since = max(starts) if starts else since
    comparable_until = min(ends) if ends else until
    if since and comparable_since:
        comparable_since = max(since, comparable_since)
    elif since:
        comparable_since = since

    caveat_parts = []
    for g in gaps:
        caveat_parts.append(f"{g['company']}: {g['reason']}")
    caveat = "; ".join(caveat_parts) if caveat_parts else None

    all_cover = len(gaps) == 0
    return CoverageResult(
        caveat=caveat,
        comparable_since=comparable_since,
        comparable_until=comparable_until or until,
        gaps=gaps,
        all_cover=all_cover,
    )
