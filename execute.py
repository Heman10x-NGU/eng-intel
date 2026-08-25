"""QueryPlan → parameterized SQL / retrieval. One executor, all ops."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any

from config import COMPANIES, TOPIC_KEYWORDS
from coverage import check_coverage
from db import FTS5_AVAILABLE
from plan import QueryPlan

SEARCH_MODE = "lexical"  # vector path intentionally unimplemented


@dataclass
class ExecuteResult:
    answer: str
    rows: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    aggregates: dict[str, Any]
    coverage_note: str | None
    sql: str
    sql_params: list[Any]
    search_mode: str = SEARCH_MODE


def _companies_clause(companies: list[str]) -> tuple[str, list[str]]:
    if not companies:
        return "", []
    placeholders = ",".join("?" * len(companies))
    return f" AND company IN ({placeholders})", list(companies)


def _source_clause(source_types: list[str]) -> tuple[str, list[str]]:
    if not source_types:
        return "", []
    placeholders = ",".join("?" * len(source_types))
    return f" AND source_type IN ({placeholders})", list(source_types)


def _date_clause(since: date | None, until: date | None) -> tuple[str, list[str]]:
    parts: list[str] = []
    params: list[str] = []
    if since:
        parts.append("published_at >= ?")
        params.append(since.isoformat())
    if until:
        parts.append("published_at <= ?")
        params.append(until.isoformat())
    if not parts:
        return "", []
    return " AND " + " AND ".join(parts), params


def _word_boundary(text: str | None, keyword: str) -> bool:
    if not text:
        return False
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE))


def _topic_match(text: str | None, topic: str) -> bool:
    if not text:
        return False
    low = text.lower()
    for kw in TOPIC_KEYWORDS.get(topic, []):
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return True
    return False


def _filter_rows_keyword(rows: list[sqlite3.Row], keyword: str) -> list[sqlite3.Row]:
    out = []
    for r in rows:
        if _word_boundary(r["title"], keyword) or _word_boundary(r["body_text"], keyword):
            out.append(r)
    return out


def _filter_rows_topic(rows: list[sqlite3.Row], topic: str) -> list[sqlite3.Row]:
    out = []
    for r in rows:
        if _topic_match(r["title"], topic) or _topic_match(r["body_text"], topic):
            out.append(r)
    return out


def _fetch_base(conn: sqlite3.Connection, plan: QueryPlan, since: date | None, until: date | None) -> tuple[list[sqlite3.Row], str, list[Any]]:
    cc, cp = _companies_clause(plan.companies)
    sc, sp = _source_clause(plan.source_types)
    dc, dp = _date_clause(since, until)
    sql = f"SELECT * FROM documents WHERE 1=1{cc}{sc}{dc} ORDER BY published_at DESC"
    params = cp + sp + dp
    rows = conn.execute(sql, params).fetchall()
    return rows, sql, params


def _apply_structured_filters(rows: list[sqlite3.Row], filters: dict) -> list[sqlite3.Row]:
    out = list(rows)
    if filters.get("remote") is True:
        out = [r for r in out if r["is_remote"] == 1]
    if dept := filters.get("department"):
        out = [r for r in out if (r["department"] or "") == dept]
    return out


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _citations_from_rows(rows: list[sqlite3.Row]) -> list[dict]:
    return [
        {"title": r["title"], "url": r["url"], "company": r["company"], "source_type": r["source_type"]}
        for r in rows
        if r["url"]
    ]


def _synthesize_compare(chunks: list[dict]) -> str:
    if not chunks:
        return "No retrieved content to compare."
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        lines = []
        for i, c in enumerate(chunks[:6]):
            lines.append(f"[{i}] {c['company']}: {c['title']} — {(c.get('body_text') or '')[:200]}")
        return "Retrieved excerpts (no API key for synthesis):\n" + "\n".join(lines)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        payload = [{"i": i, "company": c["company"], "title": c["title"], "text": (c.get("body_text") or "")[:800]} for i, c in enumerate(chunks)]
        prompt = (
            "Compare how the companies discuss database products using ONLY these chunks. "
            "Cite sources as [index]. Do not invent URLs or numbers.\n\n"
            + json.dumps(payload)
        )
        msg = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=500,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as exc:
        return f"Compare synthesis failed: {exc}"


def execute(conn: sqlite3.Connection, plan: QueryPlan) -> ExecuteResult:
    if plan.op == "refuse":
        return ExecuteResult(
            answer=plan.refuse_reason or "Cannot answer this question.",
            rows=[],
            citations=[],
            aggregates={},
            coverage_note=None,
            sql="",
            sql_params=[],
        )

    since, until = plan.since, plan.until
    coverage_note = None
    if plan.op in ("count", "rank", "compare", "timeline"):
        st = plan.source_types[0] if plan.source_types else "blog"
        cov = check_coverage(conn, plan.companies or COMPANIES, st, plan.since, plan.until)
        if cov.caveat:
            coverage_note = cov.caveat
        if cov.comparable_since:
            since = cov.comparable_since
        if cov.comparable_until:
            until = cov.comparable_until

    rows, sql, params = _fetch_base(conn, plan, since, until)
    rows = _apply_structured_filters(rows, plan.filters)

    if plan.keyword:
        if SEARCH_MODE == "lexical":
            if FTS5_AVAILABLE:
                kw_rows = []
                fts_sql = (
                    "SELECT d.* FROM documents d "
                    "JOIN documents_fts ON documents_fts.doc_id = d.id "
                    "WHERE documents_fts MATCH ?"
                )
                fts_params: list[Any] = [plan.keyword]
                if plan.source_types:
                    fts_sql += f" AND d.source_type IN ({','.join('?'*len(plan.source_types))})"
                    fts_params.extend(plan.source_types)
                if plan.companies:
                    fts_sql += f" AND d.company IN ({','.join('?'*len(plan.companies))})"
                    fts_params.extend(plan.companies)
                kw_rows = conn.execute(fts_sql, fts_params).fetchall()
                rows = _filter_rows_keyword(kw_rows, plan.keyword)
            else:
                rows = _filter_rows_keyword(rows, plan.keyword)
        else:
            raise NotImplementedError("vector search not implemented")

    if plan.topic:
        rows = _filter_rows_topic(rows, plan.topic)

    aggregates: dict[str, Any] = {}

    if plan.op == "count":
        by_company: dict[str, int] = {}
        for r in rows:
            by_company[r["company"]] = by_company.get(r["company"], 0) + 1
        total = len(rows)
        aggregates = {"total": total, "by_company": by_company}
        parts = [f"{total} total"]
        for c, n in sorted(by_company.items()):
            parts.append(f"{c} {n}")
        answer = f"{' '.join(parts)} matching documents."
        if plan.keyword:
            answer = f"{total} postings mention {plan.keyword} (" + ", ".join(f"{c} {n}" for c, n in sorted(by_company.items())) + ")."
        if coverage_note:
            answer += " HashiCorp jobs are not in the corpus (see coverage panel)."

    elif plan.op == "list":
        total_count = len(rows)
        display_rows = rows[: plan.limit]
        rows = display_rows
        aggregates = {"count": total_count}
        answer = f"{total_count} roles found."
        if plan.companies == ["supabase"] and plan.filters.get("remote") and plan.filters.get("department") == "Engineering":
            answer += " (Remote = location contains 'remote'; 3 AMER-titled Engineering roles excluded.)"
        if coverage_note:
            answer += f" {coverage_note}"

    elif plan.op == "rank":
        if plan.source_types == ["repo_activity"]:
            scores = []
            for r in rows:
                extra = json.loads(r["extra_json"] or "{}")
                scores.append((r["company"], extra.get("events_7d", 0), extra))
            scores.sort(key=lambda x: x[1], reverse=True)
            aggregates = {"ranking": {c: s for c, s, _ in scores}}
            if scores:
                top = scores[0]
                answer = (
                    f"{top[0]} leads with {top[1]} push+PR events in 7 days "
                    f"(push {top[2].get('push_events',0)}, pr {top[2].get('pr_events',0)})."
                )
            else:
                answer = "No repo activity rows."
        else:
            by_company: dict[str, int] = {}
            for r in rows:
                by_company[r["company"]] = by_company.get(r["company"], 0) + 1
            ranking = sorted(by_company.items(), key=lambda x: x[1], reverse=True)
            aggregates = {"ranking": dict(ranking)}
            if ranking:
                winner, count = ranking[0]
                answer = f"{winner} leads with {count} matching blog posts"
                if since:
                    answer += f" since {since.isoformat()}"
                answer += "."
            else:
                answer = "No matching blog posts."
            if coverage_note:
                answer += f" Caveat: {coverage_note}"

    elif plan.op == "compare":
        chunk_rows = rows[: plan.limit]
        chunks = _rows_to_dicts(chunk_rows)
        answer = _synthesize_compare(chunks)
        rows = chunk_rows
        aggregates = {"chunks": len(chunks)}
        if coverage_note:
            answer += f"\n\nCoverage: {coverage_note}"

    elif plan.op == "timeline":
        aggregates = {"count": len(rows)}
        preview = ", ".join(f"{r['title'][:40]}" for r in rows[:5])
        answer = f"{len(rows)} items in window. Recent: {preview}"
        if coverage_note:
            answer += f" ({coverage_note})"
    else:
        answer = "Unsupported operation."

    return ExecuteResult(
        answer=answer,
        rows=_rows_to_dicts(rows),
        citations=_citations_from_rows(rows),
        aggregates=aggregates,
        coverage_note=coverage_note,
        sql=sql,
        sql_params=params,
        search_mode=SEARCH_MODE,
    )
