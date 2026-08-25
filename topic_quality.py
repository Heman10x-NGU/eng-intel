"""Topic classification sanity checks for eval harness."""

from __future__ import annotations

import sqlite3

from config import TOPIC_KEYWORDS
from execute import _topic_match


def topic_identity_violations(
    conn: sqlite3.Connection,
    topic: str,
    *,
    source_type: str = "blog",
    min_posts: int = 3,
) -> list[str]:
    """Fail when every post from a company matches — usually a vendor name in the keyword set."""
    rows = conn.execute(
        "SELECT company, title, body_text FROM documents WHERE source_type = ?",
        (source_type,),
    ).fetchall()
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        co = row["company"]
        bucket = stats.setdefault(co, {"total": 0, "match": 0})
        bucket["total"] += 1
        if _topic_match(row["title"], topic) or _topic_match(row["body_text"], topic):
            bucket["match"] += 1

    errs: list[str] = []
    for company, counts in stats.items():
        total = counts["total"]
        matched = counts["match"]
        if total >= min_posts and matched == total:
            errs.append(
                f"{company}: {matched}/{total} posts match topic {topic!r} (100% — likely identity keyword)"
            )
    return errs


def q4_retrieval_violations(
    rows: list[dict],
    companies: list[str],
    topic: str,
    *,
    title_keyword_min_pct: float = 70.0,
    company_min_share: float = 1 / 3,
) -> list[str]:
    """Compare-path retrieval quality: title relevance and per-company balance."""
    if not rows:
        return ["no compare rows retrieved"]

    title_hits = sum(1 for r in rows if _topic_match(r.get("title"), topic))
    pct = 100.0 * title_hits / len(rows)
    if pct < title_keyword_min_pct:
        errs = [f"Q4 title keyword rate {pct:.0f}% < {title_keyword_min_pct:.0f}%"]
    else:
        errs = []

    min_count = len(rows) * company_min_share
    by_company: dict[str, int] = {}
    for row in rows:
        by_company[row.get("company", "")] = by_company.get(row.get("company", ""), 0) + 1
    for company in companies:
        got = by_company.get(company, 0)
        if got < min_count:
            errs.append(
                f"Q4 {company} contributed {got}/{len(rows)} rows, need >={min_count:.1f} (one third)"
            )
    return errs
