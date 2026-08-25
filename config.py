"""Company and source configuration — three companies, verified endpoints."""

from __future__ import annotations

COMPANIES = ["vercel", "supabase", "hashicorp"]

COMPANY_DISPLAY = {
    "vercel": "Vercel",
    "supabase": "Supabase",
    "hashicorp": "HashiCorp",
}

ENDPOINTS = {
    "vercel": {
        "jobs_api": "https://boards-api.greenhouse.io/v1/boards/vercel/jobs?content=true",
        "jobs_board": "https://job-boards.greenhouse.io/vercel",
        "blog_rss": "https://vercel.com/atom",
        "github_org": "vercel",
    },
    "supabase": {
        "jobs_api": "https://api.ashbyhq.com/posting-api/job-board/supabase",
        "blog_rss": "https://supabase.com/rss.xml",
        "github_org": "supabase",
    },
    "hashicorp": {
        "careers_url": "https://www.hashicorp.com/careers/open-positions",
        "blog_rss": "https://www.hashicorp.com/blog/feed.xml",
        "github_org": "hashicorp",
    },
}

FIXTURE_PATHS = {
    "vercel_jobs": "fixtures/vercel_jobs_greenhouse.json",
    "supabase_jobs": "fixtures/supabase_jobs_ashby.json",
    "vercel_blog": "fixtures/vercel_blog_atom.xml",
    "supabase_blog": "fixtures/supabase_blog_rss.xml",
    "hashicorp_blog": "fixtures/hashicorp_blog_rss.xml",
    "hashicorp_jobs_raw": "fixtures/hashicorp_jobs_raw.json",
    "github_vercel": "fixtures/github_vercel_events.json",
    "github_supabase": "fixtures/github_supabase_events.json",
    "github_hashicorp": "fixtures/github_hashicorp_events.json",
}

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "databases": [
        "postgres",
        "postgresql",
        "pgvector",
        "database",
        "databases",
        "sql",
        "prisma",
        "drizzle",
        "mysql",
        "mongodb",
        "redis",
        "kv",
        "storage engine",
    ],
}

# Company / vendor names must never appear in topic sets (identity ≠ subject).
TOPIC_FORBIDDEN_TERMS = frozenset(COMPANIES) | frozenset({"neon", "planetscale", "vercel"})
for _topic, _kws in TOPIC_KEYWORDS.items():
    _overlap = TOPIC_FORBIDDEN_TERMS & {k.lower() for k in _kws}
    if _overlap:
        raise ValueError(f"topic {_topic!r} contains vendor/company names: {sorted(_overlap)}")

SOURCE_TYPES = ["job", "blog", "repo_activity"]

DB_PATH = "data.db"
