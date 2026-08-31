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

REFUSAL_HELP = (
    "Supported questions count jobs or blogs, list roles, rank companies, "
    "compare messaging, or show a recent-content timeline. "
    "Example: How many job postings across these companies mention Rust?"
)


def _refuse(reason: str) -> QueryPlan:
    return QueryPlan(op="refuse", refuse_reason=f"{reason} {REFUSAL_HELP}")


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


KEYWORD_STOPWORDS = {
    "remote", "engineering", "these", "those", "this", "that", "all", "the",
    "a", "an", "each", "both", "our", "their", "any", "full", "part", "contract",
    "hybrid", "onsite", "databases", "database", "open", "recent", "new",
    "active", "across", "companies", "company", "there", "here", "now", "total",
    "how", "many", "much", "more", "most", "few", "fewer", "other", "such",
    "what", "which", "who", "whom", "whose", "where", "when", "why",
    "show", "list", "count", "post", "posts", "posting", "postings", "role",
    "roles", "job", "jobs", "position", "positions", "available", "current",
    "shipped", "come", "out", "published", "released", "done", "been",
    "vercel", "supabase", "hashicorp", "hashi",
}

COMMON_TECH_KEYWORDS = {
    "rust", "python", "golang", "go", "typescript", "javascript", "java",
    "cpp", "c++", "c#", "csharp", "ruby", "swift", "kotlin", "elixir", "scala",
    "react", "nextjs", "next.js", "vue", "svelte", "tailwind",
    "postgres", "postgresql", "mysql", "redis", "kafka", "sqlite",
    "kubernetes", "k8s", "docker", "terraform", "aws", "gcp", "azure",
    "graphql", "grpc", "rest",
}


def _detect_keyword(q: str) -> str | None:
    low = q.lower()

    # 1. Direct match for known technologies (handles symbols like c#, c++, next.js)
    for tech in sorted(COMMON_TECH_KEYWORDS, key=len, reverse=True):
        escaped = re.escape(tech)
        pat = rf"(?:\b|^){escaped}(?:\b|$|\s|[^\w])"
        if re.search(pat, low):
            return tech

    # 2. Explicit mention / requirement phrasing: 'mentioning foo', 'requires foo', 'using foo'
    m = re.search(
        r"\b(?:mention(?:ing|s)?|need(?:ing|s)?|us(?:e|es|ing)|requir(?:e|es|ing))\s+([a-zA-Z0-9_\+#\.\-]+)",
        low,
    )
    if m:
        cand = m.group(1).strip(".?,!")
        if cand not in KEYWORD_STOPWORDS and len(cand) > 1:
            return cand

    # 3. Phrasing with 'with / for / have / has' followed by a valid non-stopword identifier
    m2 = re.search(r"\b(?:with|for|have|has)\s+([a-zA-Z0-9_\+#\.\-]+)\b", low)
    if m2:
        cand = m2.group(1).strip(".?,!")
        if cand not in KEYWORD_STOPWORDS and len(cand) > 1:
            return cand

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
    if not q:
        return _refuse("Question is empty.")
    op = _detect_op(q)
    if op is None:
        return _refuse("Could not map this question to jobs, blogs, GitHub activity, or a comparison.")
    if op == "refuse":
        return QueryPlan(
            op="refuse",
            refuse_reason=(
                "Question is outside corpus scope (not about jobs, blogs, or GitHub activity). "
                + REFUSAL_HELP
            ),
        )

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

    if op in ("count", "list", "rank", "timeline") and not source_types:
        return _refuse("Could not tell whether this is about jobs, blogs, or GitHub activity.")

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


def _unparsed_words(question: str, plan: QueryPlan) -> list[str]:
    if plan.keyword or plan.topic:
        return []
    low = question.lower()
    words = re.findall(r"\b[a-zA-Z0-9_\+#\.\-]+\b", low)
    ignore = (
        KEYWORD_STOPWORDS
        | set(COMPANIES)
        | {
            "job", "jobs", "role", "roles", "posting", "postings", "position", "positions",
            "blog", "blogs", "post", "posts", "github", "repo", "repos", "repository",
            "mention", "mentions", "mentioning", "need", "needs", "using", "use", "with",
            "in", "for", "have", "has", "are", "is", "be", "do", "does", "did", "corpus",
            "content", "item", "items", "document", "documents", "data", "tell", "me",
            "show", "list", "count", "rank", "compare", "timeline",
        }
    )
    return [w for w in words if w not in ignore and len(w) > 1 and not w.isdigit()]


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


def _call_llm_json(prompt: str) -> dict[str, Any] | None:
    # 1. DeepSeek (primary)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        try:
            import httpx

            resp = httpx.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
                timeout=8.0,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
                return json.loads(text)
        except Exception:
            pass

    # 2. Anthropic (fallback)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key)
            msg = client.messages.create(
                model="claude-3-5-haiku-latest",
                max_tokens=300,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
            return json.loads(text)
        except Exception:
            pass

    return None


def llm_fill(question: str, plan: QueryPlan, missing: list[str]) -> QueryPlan:
    prompt = f"""Fill or correct QueryPlan slots as JSON for an engineering intelligence warehouse.
Question: {question}
Current plan: {json.dumps(plan.to_dict())}
Slots needing resolution: {missing}
Valid companies: {COMPANIES}
Valid source_types: ["job", "blog", "repo_activity"]
Valid ops: ["count", "list", "rank", "compare", "timeline", "refuse"]
Rules:
- If out of corpus scope (revenue, stock prices, CEO names, off-topic), set op to "refuse" and refuse_reason.
- If searching for a tech/skill keyword (e.g. rust, golang, elixir), set keyword to that term.
- Never invent numbers. Return JSON only."""
    data = _call_llm_json(prompt)
    if not data:
        return plan
    try:
        merged = {**plan.to_dict(), **data}
        validated = QueryPlanModel.model_validate(merged)
        return QueryPlan(**validated.model_dump())
    except ValidationError:
        return plan


def build_plan(question: str) -> QueryPlan:
    plan = rule_fill(question)
    missing = _missing_required(plan)
    unparsed = _unparsed_words(question, plan)
    if unparsed:
        missing.append("keyword")

    if missing:
        plan = llm_fill(question, plan, missing)
    return plan
