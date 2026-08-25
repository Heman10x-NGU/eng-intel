# eng-intel

Local engineering intelligence warehouse for **Vercel**, **Supabase**, and **HashiCorp**. Ask natural-language questions about what they hire for, publish on engineering blogs, and ship on GitHub — with citations and a visible **QueryPlan** for every answer.

## Quick start

```bash
python3.11 -m venv .venv --upgrade-deps
.venv/bin/pip install -r requirements.txt
make seed    # builds data.db from fixtures — no network, no API key
make run     # http://127.0.0.1:8000
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
| Grounding guard | Strips unbacked URLs and integers |
| Playwright selector scrape + accuracy oracle | Scored against Greenhouse ground truth |
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

- Playwright selector scrape finds ~58% of Vercel jobs (pagination/hydration).
- Supabase `isRemote` is null in API — remote derived from location string (21 eng remote vs 18 strict probe; heuristic difference).
- GitHub activity uses one API page per org, not full 7-day pagination.
- Compare answers without `ANTHROPIC_API_KEY` return retrieved excerpts, not synthesized prose.

## Another week

- Paginate GitHub events properly; backfill HashiCorp blog beyond RSS cap.
- Improve Playwright selectors to 86/86; run browser-use discovery with API key.
- Embeddings for `compare` ranking only; scheduled ingest worker.

## Time spent

~10.5 hours (see `TIMELOG.md`).
