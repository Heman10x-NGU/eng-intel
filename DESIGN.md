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
- **No job board** (HashiCorp) → zero rows, ledger explains IBM redirect.
- **Null API fields** (Supabase `isRemote`) → derived flags in `extra_json`, disclosed in README.
- **GitHub 403** → falls back to last committed fixture.

## Scale: 50 companies × 500 documents

- **Query:** ~25k rows — SQLite + indexes on `(company, source_type, published_at)` and FTS5 stay fine.
- **Ingest:** breaks first — 50 ATS sources, bot walls, backoff, scheduled workers; coverage ledger becomes essential.
- **Compare:** can't stuff 25k docs in a prompt — top-k retrieval + optional embeddings for ranking only.
