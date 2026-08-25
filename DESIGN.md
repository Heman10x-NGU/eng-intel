# Design note — eng-intel

## How the query layer routes question types

Every question becomes a **QueryPlan** (`op`, `companies`, `source_types`, `keyword`, `topic`, `since`/`until`, `filters`, `group_by`, `metric`).

1. **Rules** (`plan.py`) fill slots from regex — companies, ops, keywords, relative dates (`temporal.py`), filters. Zero model calls.
2. **LLM slot-fill** (optional, temp 0, pydantic) only when required slots are empty.
3. **Executor** (`execute.py`) compiles the plan:
   - `count` / `list` / `rank` / `timeline` → parameterized SQL + FTS lexical match (`search_mode=lexical`)
   - `compare` → retrieve top-k blog chunks, then one synthesis call citing by index
4. **Coverage** (`coverage.py`) intersects requested windows with `ingest_runs` before cross-company count/rank/compare.
5. **Guard** (`guard.py`) strips URLs and integers not in the result set.

The UI always shows the filled QueryPlan JSON beside the answer.

## Adding a fourth company

1. Add endpoints to `config.py` (`ENDPOINTS`, `FIXTURE_PATHS`).
2. Capture fixtures (`make ingest` once) and commit under `fixtures/`.
3. Extend ingest modules — no schema change (one `documents` table).
4. Add company alias in `plan.py` rule filler.
5. New `ingest_runs` rows record coverage automatically.

## Bad or missing data

- **Truncated RSS** → `ingest_runs.truncated=1` + note; Q2 re-ranks on shared window.
- **Degraded ingest** → `ingest_runs.degraded=1` when rows exist but dates are unparseable (`coverage_start` null); company excluded from time-window rankings with stated reason. Unit-tested in `tests/test_degraded_ingest.py`.
- **No job board** (HashiCorp) → zero rows, ledger explains IBM redirect.
- **Null API fields** (Supabase `isRemote`) → remote derived from location text only; raw Ashby field kept in `extra_json`.
- **GitHub 403** → falls back to last committed fixture.

## Eval harness

`expect_plan` asserts routing. `expect_result` asserts answers where ground truth is known — would have caught the Supabase RFC-822 date bug via `blog_null_dates: 0` and Q2 `ranking_includes: [supabase]`.

## Scale: 50 companies × 500 documents

- **Query:** ~25k rows — SQLite + indexes on `(company, source_type, published_at)` and FTS5 stay fine.
- **Ingest:** breaks first — 50 ATS sources, bot walls, backoff, scheduled workers; coverage ledger becomes essential.
- **Compare:** can't stuff 25k docs in a prompt — top-k retrieval + optional embeddings for ranking only.
