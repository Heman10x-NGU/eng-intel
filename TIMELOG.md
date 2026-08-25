# TIMELOG — section 10 blocks + V2 fixes

| Block | Target | Actual | Notes |
|---|---|---|---|
| 0.0–0.5 repo, schema, config | 30m | 35m | Both tables + FTS5 UNINDEXED columns |
| 0.5–1.5 jobs ATS + fixtures | 60m | 55m | 146 job rows (87 Vercel + 59 Supabase) |
| 1.5–2.5 blogs + GitHub + coverage | 60m | 50m | HashiCorp blog truncated flagged |
| 2.5–4.5 plan + execute + guard | 120m | 130m | FTS join fix; source_type rule tweak for Q1 |
| 4.5–6.5 Playwright + oracle | 120m | 70m | 50/87 selector recall; oracle JSON committed |
| 6.5–6.75 Cloak + HashiCorp exclusion | 15m | 20m | Fixture + SOURCE_NOTES; zero rows inserted |
| 6.75–8.25 browser-use agent | 90m | 15m | Skipped live run; trace artifact only |
| 8.25–9.0 HTML UI | 45m | 40m | Linear-inspired tokens, four blocks |
| 9.0–10.0 evals | 60m | 45m | 20/20 pass (initial) |
| 10.0–11.0 README + DESIGN + TIMELOG | 60m | 50m | — |

**Initial build: ~10h 30m**

## V2 review fixes (2026-08-26)

| Fix | Time | Commit |
|---|---|---|
| FIX-1 RFC-822 blog dates | 25m | `fix(ingest): parse RFC-822 feed dates` |
| FIX-2 degraded ledger flag | 30m | `fix(coverage): flag degraded ingests` |
| FIX-3 expect_result evals | 35m | `test(evals): assert on query results` |
| FIX-5 Q3 remote rule (18) | 20m | `fix(ingest): derive remote only from location text` |
| FIX-4 Playwright diagnosis | 45m | `fix(browser): correct Playwright selectors` |
| Docs update | 20m | `docs: sync README and design after V2 fixes` |

**V2 fixes: ~2h 55m · Grand total after V2: ~13h 25m**

## V3 demo-blocker fixes (2026-08-26)

| Fix | Time | Commit |
|---|---|---|
| C2 end-of-day `until` date bounds | 15m | `fix(execute): normalize until dates to end of day` |
| C1 guard model text only | 35m | `fix(guard): apply grounding guard to model synthesis only` |
| C3 compare extractive fallback | 40m | `fix(compare): extractive fallback without surfacing exceptions` |
| H1 computed filter exclusion notes | 20m | `fix(execute): derive filter exclusion counts from rows` |
| H2 `make test` recipe | 10m | `fix(makefile): wire make test to unittest discovery` |
| H3 timeline `plan.limit` | 15m | `fix(execute): apply plan limit to timeline results and citations` |
| Rendered-answer evals | 25m | `test(evals): assert rendered answers for six graded queries` |
| Docs + UI example buttons | 20m | `docs: sync README and design after V3 fixes` |

**V3 fixes: ~3h · Grand total: ~16h 25m**
