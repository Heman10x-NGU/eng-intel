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
| a11y tree + DeepSeek extraction | 50/87 recall, **100% field accuracy** on matched URLs — same embed cap as selectors |
| browser-use agent discovery (DeepSeek) | JSON-path fix: 16/87 engineering roles extracted; FC path fails for flash and deepseek-chat |
| CloakBrowser path + HashiCorp exclusion | Zero job rows inserted; reason in ledger |
| Plain HTML UI | Answer · QueryPlan JSON · coverage · citations |

| Stubbed | Notes |
|---|---|
| VLM screenshot extraction | Skipped — README time prioritized |
| Vector / embeddings search | `search_mode=lexical` only; hook left in executor |

| Skipped (deliberately) | Auth, deploy, admin, trending, dynamic companies, changelog, text-to-SQL, LangGraph |

## Source choices and tradeoffs

- **Vercel + Supabase jobs:** public ATS JSON — full descriptions, no browser needed.
- **HashiCorp jobs:** bot wall → CloakBrowser works, but redirect yields IBM keyword hits → **not indexed**.
- **Blogs:** RSS; feed depth differs (Vercel 2016→, Supabase 2021→, HashiCorp ~2 months).
- **GitHub:** org events API (first page); token optional for rate limits.

Browser bonus: seven scored rows against the same 87-job Greenhouse ground truth (`artifacts/scrape_accuracy.json`).

| Method | Found /87 | Field acc. | Wall clock | Cost | Beats bot wall | Brief tier |
|---|---|---|---|---|---|---|
| Greenhouse API | 87 | 1.00 | ~1s | $0 | n/a | baseline |
| Playwright selectors | 50 | 0.967 | 4.4s | $0 | no | solid |
| CloakBrowser | n/a (HashiCorp) | — | ~10s | $0 | **yes** | solid+ |
| a11y tree + DeepSeek | 50 | 1.00 | 83s | ~$0.01 | no | **stronger** |
| browser-use agent (JSON path) | 16 | 0.646 | 39s | ~$0.019 | no | **strongest** |
| browser-use agent FC flash | 0 | 0.00 | 27s | ~$0.007 | no | FC schema collapse |
| browser-use agent FC deepseek-chat | 0 | 0.00 | 16s | ~$0.002 | no | FC schema collapse |

**Embed cap finding:** the a11y method and the Playwright selector method both stop at **50/87 with the same missed URLs** — two independent methods hitting the identical boundary is evidence the Greenhouse embed cap is structural, not a selector defect. a11y improves field accuracy on matched rows (1.00 vs 0.967) but does not clear recall.

**Agent schema finding:** function-calling `AgentOutput` fails for both `deepseek-v4-flash` and `deepseek-chat` (flat action args instead of wrapper). Trimming the action registry to seven tools plus forcing DeepSeek's `json_object` path fixes the loop; the successful run extracts engineering-filtered roles only (16/87).

**Agent cost basis:** `cost_usd` sums token counts from DeepSeek API `usage` fields captured in a `ChatDeepSeekJSON` subclass, priced at DeepSeek V4 off-peak rates when browser-use's `total_cost` is zero.

Run: `make browser-oracle` (after `make browser-a11y` and `make browser-agent` with `DEEPSEEK_API_KEY` in `.env`).

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
- browser-use agent: function-calling path **fails** (action-union schema collapse); JSON-path subclass + trimmed tools **succeeds** for engineering-filtered extraction — traces in `fixtures/vercel_agent_*.json`.

## Another week

- Paginate GitHub events properly; backfill HashiCorp blog beyond RSS cap.
- browser-use discovery with API key; embeddings only if lexical scoring stops being enough at ~50 companies.

## Evals

`make eval` — **28** cases: plan routing, `expect_result` (including topic-identity and Q4 retrieval quality), and **`expect_rendered`** on all six graded demo queries.

## Time spent

**~4 hours end to end** including planning and review rounds before and between commits; **~1h 45m** of that is visible in git commit timestamps (first commit `2026-08-26 01:02 IST` through V5 at `02:47 IST`, plus V6 fixes in the same session). Do not cite the brief's planned block estimates (~21h) as hours worked.
