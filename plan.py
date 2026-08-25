"""NL → QueryPlan: rules first, LLM slot-fill for gaps only."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from config import COMPANIES, TOPIC_KEYWORDS
from temporal import parse_relative_window

Op = Literal["count", "list", "rank", "compare", "timeline", "refuse"]
GroupBy = Literal["company", "source_type"] | None


@dataclass
class QueryPlan:
    op: Op
    companies: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    keyword: str | None = None
    topic: str | None = None
    since: date | None = None
    until: date | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: GroupBy = None
    metric: str | None = None
    limit: int = 20
    refuse_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["since"] = self.since.isoformat() if self.since else None
        d["until"] = self.until.isoformat() if self.until else None
        return d


class QueryPlanModel(BaseModel):
    op: Literal["count", "list", "rank", "compare", "timeline", "refuse"]
    companies: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    keyword: str | None = None
    topic: str | None = None
    since: date | None = None
    until: date | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    group_by: Literal["company", "source_type"] | None = None
    metric: str | None = None
    limit: int = 20
    refuse_reason: str | None = None


COMPANY_ALIASES = {
    "vercel": "vercel",
    "supabase": "supabase",
    "hashicorp": "hashicorp",
    "hashi": "hashicorp",
}


def _detect_companies(q: str) -> list[str]:
    found = []
    low = q.lower()
    for alias, canonical in COMPANY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", low):
            found.append(canonical)
    return list(dict.fromkeys(found))


def _detect_op(q: str) -> Op | None:
    low = q.lower()
    if any(x in low for x in ("revenue", "stock price", "valuation", "market cap")):
        return "refuse"
    if re.search(r"\bcompare\b|\bvs\.?\b| versus ", low):
        return "compare"
    if re.search(r"\b(show|list|what are)\b", low) and re.search(r"\b(role|job|position)", low):
        return "list"
    if re.search(r"\bhow many\b|\bcount\b", low):
        return "count"
    if re.search(r"\bmost\b|\bwhich company\b|\brank\b|\bleads?\b|\btop\b", low):
        return "rank"
    if re.search(r"\bnew content\b|\bwhat('s| is) new\b|\btimeline\b|\brecent\b", low):
        return "timeline"
    return None


def _detect_source_types(q: str, op: Op | None) -> list[str]:
    low = q.lower()
    types: list[str] = []
    if re.search(r"\b(job|role|posting|position|hire|opening)s?\b", low):
        types.append("job")
    if re.search(r"\bblog\b|\barticle", low) or (re.search(r"\bpost", low) and "posting" not in low and "postgres" not in low):
        types.append("blog")
    if re.search(r"\bgithub|repo|repository\b", low) or (op == "rank" and re.search(r"\bactive\b", low)):
        types.append("repo_activity")
    if not types:
        if op in ("count", "list") and re.search(r"\bremote\b|\bengineer", low):
            types = ["job"]
        elif op == "timeline":
            types = ["job", "blog", "repo_activity"]
        elif op == "rank" and re.search(r"\bdatabase", low):
            types = ["blog"]
        elif op == "compare":
            types = ["blog"]
        elif op == "rank":
            types = ["repo_activity"]
    return types


def _detect_keyword(q: str) -> str | None:
    low = q.lower()
    m = re.search(r"\bmention(?:ing|s)?\s+(\w+)", low)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:need|using|with)\s+(\w+)\b", low)
    if m and m.group(1) not in ("remote", "engineering"):
        return m.group(1)
    for lang in ("rust", "python", "go", "typescript", "javascript", "java"):
        if re.search(rf"\b{lang}\b", low):
            return lang
    return None


def _detect_topic(q: str) -> str | None:
    low = q.lower()
    if re.search(r"\bdatabase", low):
        return "databases"
    for topic in TOPIC_KEYWORDS:
        if topic in low:
            return topic
    return None


def _detect_filters(q: str) -> dict[str, Any]:
    low = q.lower()
    filters: dict[str, Any] = {}
    if re.search(r"\bremote\b", low):
        filters["remote"] = True
    if re.search(r"\bengineering\b", low):
        filters["department"] = "Engineering"
    return filters


def rule_fill(question: str) -> QueryPlan:
    q = question.strip()
    op = _detect_op(q) or "count"
    if op == "refuse":
        return QueryPlan(op="refuse", refuse_reason="Question is outside corpus scope (not about jobs, blogs, or GitHub activity).")

    companies = _detect_companies(q)
    source_types = _detect_source_types(q, op)
    keyword = _detect_keyword(q)
    topic = _detect_topic(q)
    since, until = parse_relative_window(q)
    filters = _detect_filters(q)
    group_by: GroupBy = None
    metric = None
    limit = 20

    low = q.lower()
    if op == "rank" and source_types == ["blog"]:
        group_by = "company"
    if op == "rank" and source_types == ["repo_activity"]:
        group_by = "company"
        metric = "events_7d"
    if op == "compare":
        if len(companies) < 2:
            companies = ["vercel", "supabase"]
        source_types = source_types or ["blog"]
        topic = topic or "databases"

    return QueryPlan(
        op=op,
        companies=companies,
        source_types=source_types,
        keyword=keyword,
        topic=topic,
        since=since,
        until=until,
        filters=filters,
        group_by=group_by,
        metric=metric,
        limit=limit,
    )


def _missing_required(plan: QueryPlan) -> list[str]:
    missing = []
    if plan.op == "refuse":
        return missing
    if not plan.source_types:
        missing.append("source_types")
    if plan.op == "compare" and len(plan.companies) < 2:
        missing.append("companies")
    if plan.op == "rank" and plan.source_types == ["repo_activity"] and not plan.metric:
        missing.append("metric")
    return missing


def llm_fill(question: str, plan: QueryPlan, missing: list[str]) -> QueryPlan:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return plan
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""Fill only these missing QueryPlan slots as JSON. Temperature 0 rules apply.
Question: {question}
Current plan: {json.dumps(plan.to_dict())}
Missing slots: {missing}
Valid companies: {COMPANIES}
Valid source_types: job, blog, repo_activity
Valid ops: count, list, rank, compare, timeline, refuse
Never invent numbers. Return JSON only."""
        msg = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=300,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        merged = {**plan.to_dict(), **data}
        validated = QueryPlanModel.model_validate(merged)
        return QueryPlan(**validated.model_dump())
    except Exception:
        return plan


def build_plan(question: str) -> QueryPlan:
    plan = rule_fill(question)
    missing = _missing_required(plan)
    if missing:
        plan = llm_fill(question, plan, missing)
    return plan
