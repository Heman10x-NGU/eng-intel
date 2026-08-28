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
make eval    # 32 plan + result + rendered-answer cases
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
| browser-use agent discovery (DeepSeek) | **15/15** engineering roles (task-scoped); navigates vercel.com autonomously |
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

Browser bonus: scored rows in `artifacts/scrape_accuracy.json`. Selector and a11y methods use the **full board** (87 jobs); the agent task asked for **engineering roles only** (15 in ground truth), so its primary row uses that scope. Raw string field scores understate cross-page extractors — see normalized columns below.

| Method | Scope | Found | Title | Location (norm) | Dept | Wall clock | Cost | Tier |
|---|---|---|---|---|---|---|---|---|
| Greenhouse API | full board | 87/87 | 1.00 | 1.00 | 1.00 | ~1s | $0 | baseline |
| Playwright selectors | full board | 50/87 | 0.90 | 1.00 | 1.00 | 4.4s | $0 | solid |
| CloakBrowser | full board | — | — | — | — | ~10s | $0 | beats bot wall |
| a11y tree + DeepSeek | full board | 50/87 | 1.00 | 1.00 | 1.00 | 83s | ~$0.01 | stronger |
| **browser-use agent** | **engineering only** | **15/15** | **1.00** | **1.00** | **1.00** | **39s** | **~$0.02** | **strongest** |
| browser-use agent (also) | full board | 16/87 | 1.00 | 1.00† | 0.94† | 39s | ~$0.02 | — |
| browser-use agent FC flash | engineering only | 0/15 | — | — | — | 27s | ~$0.007 | FC blocked |
| browser-use agent FC deepseek-chat | engineering only | 0/15 | — | — | — | 16s | ~$0.002 | FC blocked |

†Per-field scores on the 16 URL-matched rows against the full board. Location exact-match is 0.00 because Greenhouse prefixes work-model tags (`Hybrid -`, `Remote -`) that `vercel.com/careers` renders separately; set comparison fixes this (1.00).

**Tradeoff (what the brief grades):** the agent was told to find engineering roles starting from vercel.com. It navigated there on its own, found the listing, and extracted **15 of 15 engineering roles with exact title matches** in ~39s for ~$0.02 — versus ~1s and $0 for the API. That is the honest trade: the agent is the only method that would still work if they redesigned the page tomorrow, and it is roughly a hundred times slower.

**Embed cap finding:** the a11y method and the selector method stop at the same **50/87 with the same missed URLs**, which is evidence the Greenhouse embed cap is structural rather than a selector defect. a11y improves title accuracy on matched rows (1.00 vs 0.90) but does not clear recall.

**Agent schema note:** function-calling `AgentOutput` fails against DeepSeek models — a known upstream issue in browser-use ([#3544](https://github.com/browser-use/browser-use/issues/3544), [#2529](https://github.com/browser-use/browser-use/issues/2529)). Routed around with a ~25-line `ChatDeepSeekJSON` subclass forcing `response_format=json_object` plus a trimmed seven-action registry; traces in `fixtures/vercel_agent_*.json`.

**Vision tier:** `deepseek-v4-flash-vision-exp` is on this API key and browser-use already serializes image parts, but the a11y-tree path already covers that tier at lower cost — skipped a screenshot/VLM row.

**Agent cost basis:** `cost_usd` sums token counts from DeepSeek API `usage` fields captured in `ChatDeepSeekJSON`, priced at DeepSeek V4 off-peak rates when browser-use's `total_cost` is zero.

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
- browser-use agent: **15/15** engineering roles on the scoped task (oracle was dividing by 87); function-calling blocked by upstream browser-use issues [#3544](https://github.com/browser-use/browser-use/issues/3544) / [#2529](https://github.com/browser-use/browser-use/issues/2529), routed around with JSON-path subclass — traces in `fixtures/vercel_agent_*.json`.

## Another week

- Paginate GitHub events properly; backfill HashiCorp blog beyond RSS cap.
- browser-use discovery with API key; embeddings only if lexical scoring stops being enough at ~50 companies.

## Evals

`make eval` — **32** cases: plan routing, `expect_result` (including topic-identity and Q4 retrieval quality), **`expect_rendered`** on all six graded demo queries, and refuse-path coverage for empty/gibberish/off-topic input.

## Time spent

**~4 hours end to end** including planning and review rounds before and between commits; **~1h 45m** of that is visible in git commit timestamps (first commit `2026-08-26 01:02 IST` through V5 at `02:47 IST`, plus V6 fixes in the same session). Do not cite the brief's planned block estimates (~21h) as hours worked.
