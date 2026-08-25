# eng-intel

Local engineering intelligence warehouse for **Vercel**, **Supabase**, and **HashiCorp**. Ask natural-language questions about what they hire for, publish on engineering blogs, and ship on GitHub — with citations and a visible **QueryPlan** for every answer.

## Where to look

| Area | Files |
|---|---|
| Ingest | `ingest_jobs_api.py`, `ingest_blogs.py`, `ingest_github.py`, `ingest_jobs_browser.py`, `normalize.py`, `seed.py` |
| Query layer | `plan.py` (+ `temporal.py` for relative date rules) → `execute.py` → `guard.py` |
| Coverage ledger | `ingest_runs` via `normalize.write_run`, read in `coverage.py` |
| Everything else | `config.py`, `db.py`, `app.py`, `static/index.html`, `evals/` |

## Quick start

```bash
python3.11 -m venv .venv --upgrade-deps
.venv/bin/pip install -r requirements.txt
make seed    # builds data.db from fixtures — no network, no API key
make run     # http://127.0.0.1:8000
make test    # unit tests (degraded ingest)
make eval    # 27 plan + result + rendered-answer cases
```

Optional live refresh: `INGEST_LIVE=1 make ingest` (needs network; `GITHUB_TOKEN` optional).

## User and job-to-be-done

A recruiter, investor, or engineer tracking these three companies wants one place to ask: *How many roles mention Rust?* *Who blogs most about databases?* *What shipped this month?* — without re-scraping the web on every question.

## What I built vs stubbed vs skipped

| Built | Notes |
|---|---|
| SQLite warehouse (`documents` + `ingest_runs` coverage ledger) | FTS5 with UNINDEXED scope columns (Palimp pattern) |
| Jobs via Greenhouse + Ashby JSON | 146 job rows from committed fixtures |
| Blogs via RSS | HashiCorp feed flagged `truncated` (20 items) |
| GitHub org events rollup | Push+PR metric over 7 days |
| QueryPlan IR + single executor | Rules fill slots; LLM only for gaps / compare synthesis |
| Grounding guard | Strips unbacked URLs/integers from **model synthesis only** (`render_answer` in `app.py`); executor template text is trusted |
| Playwright selector scrape + accuracy oracle | 50/87 recall (embed cap); **97% field accuracy** — see `docs/PLAYWRIGHT_VERCEL_DIAGNOSIS.md` |
| CloakBrowser path + HashiCorp exclusion | Zero job rows inserted; reason in ledger |
| Plain HTML UI | Answer · QueryPlan JSON · coverage · citations |

| Stubbed | Notes |
|---|---|
| browser-use agent tier | Optional `[agent]` group; trace artifact when no API key |
| VLM screenshot extraction | Skipped — README time prioritized |
| Vector / embeddings search | `search_mode=lexical` only; hook left in executor |

| Skipped (deliberately) | Auth, deploy, admin, trending, dynamic companies, changelog, text-to-SQL, LangGraph |

## Source choices and tradeoffs

- **Vercel + Supabase jobs:** public ATS JSON — full descriptions, no browser needed.
- **HashiCorp jobs:** bot wall → CloakBrowser works, but redirect yields IBM keyword hits → **not indexed**.
- **Blogs:** RSS; feed depth differs (Vercel 2016→, Supabase 2021→, HashiCorp ~2 months).
- **GitHub:** org events API (first page); token optional for rate limits.

Browser bonus: measured Playwright vs API on the same 86/87 Vercel board (`artifacts/scrape_accuracy.json`).

## Supabase remote-engineering rule (Q3)

Ashby returns `isRemote: null` on most rows; some AMER-titled roles have `isRemote: true` without "remote" in the location string.

**Rule:** `is_remote` is derived only when `location` contains the word **remote** (word boundary). Bare regions (`AMER`, `APAC`) are not treated as remote even if Ashby flags them — the raw `ashby_is_remote_raw` field stays in `extra_json` for audit.

Three-way split on Engineering roles (fixture, Aug 2026):

| Bucket | Count | Examples |
|---|---|---|
| Location contains "remote" | **18** | `Remote, Anywhere` — **used for Q3** |
| Bare region only | 3 | `AMER` — OrioleDB Developer, IAM Engineer, API Engineer |
| On-site / hybrid | 0 | — |

Eval pins Q3 at **18** rows, all `department=Engineering`.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | One stack for ingest + SQL + HTTP |
| App | FastAPI + uvicorn | Two endpoints, easy live edits |
| Store | SQLite + FTS5 | Inspectable single file; Postgres at ~50 companies |
| Query | QueryPlan IR | Variants without new handlers; model never emits SQL |
| Model | Haiku (optional) | Slot-fill + compare prose only; **never counts** |
| UI | Plain HTML + fetch | Brief says plain HTML is fine |

## Where AI helped / didn't

- **Helped:** scaffolding ingest normalizers, FTS trigger boilerplate, eval YAML harness.
- **Didn't:** ground-truth counts (verified with SQL), coverage intersection logic, HashiCorp exclusion judgment — those were probed manually and encoded as rules.

## What's fake or broken

- Playwright selector scrape: **50/87 recall** — Greenhouse embed SSR cap, not bad scrolling (diagnosed).
- GitHub activity uses one API page per org, not full 7-day pagination.
- **Topic classification is keyword-based** (`config.TOPIC_KEYWORDS`), not embeddings or a model. The failure mode is matching **company identity** instead of subject — e.g. when `supabase` was in the `databases` keyword list, every Supabase post matched (100%). Vendor names are now forbidden in topic sets, and `data_quality_topic_identity` fails if any company hits 100% on a topic. Compare retrieval uses scored lexical ranking (title-weighted, length-normalized, top-k per company) — vectors would be the next step, not a missing foundation.
- Compare answers without `ANTHROPIC_API_KEY` (or without `anthropic` installed) return a labeled extractive bullet list from retrieved posts — not synthesized prose.
- browser-use agent tier not run live (skip trace only).

## Another week

- Paginate GitHub events properly; backfill HashiCorp blog beyond RSS cap.
- browser-use discovery with API key; embeddings only if lexical scoring stops being enough at ~50 companies.

## Evals

`make eval` — **28** cases: plan routing, `expect_result` (including topic-identity and Q4 retrieval quality), and **`expect_rendered`** on all six graded demo queries.

## Time spent

~17 hours including V2–V4 review fixes (see `TIMELOG.md`).
