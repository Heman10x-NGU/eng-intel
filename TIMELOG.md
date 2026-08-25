# TIMELOG — section 10 blocks

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
| 9.0–10.0 evals | 60m | 45m | 20/20 pass |
| 10.0–11.0 README + DESIGN + TIMELOG | 60m | 50m | — |

**Total: ~10h 30m**
