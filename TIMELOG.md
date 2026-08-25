# TIMELOG

## Measured wall clock (git)

| Milestone | Timestamp (IST) | Commit |
|---|---|---|
| First commit | 2026-08-26 **01:02** | `chore: bootstrap repo tooling and dependencies` |
| Initial build complete | 2026-08-26 **01:02–01:15** (batched) | schema through UI + evals |
| V2 fixes done | 2026-08-26 **~01:30** | `docs: sync README and design after V2 fixes` |
| V3 fixes done | 2026-08-26 **~02:00** | `docs: sync README and design after V3 fixes` |
| V4 fixes done | 2026-08-26 **~02:15** | `docs: sync README and design after V4 retrieval fixes` |
| V5 browser tiers done | 2026-08-26 **02:47** | `docs: sync README and design after V5 browser tiers` |
| V6 agent schema fix | 2026-08-26 **~03:30** | model probe, trimmed tools, JSON-path subclass, oracle table |

**Total elapsed effort: ~4 hours end to end** (planning + review + commits). **~1h 45m** of that sits in the V1–V5 commit history (01:02 → 02:47 IST); V6 fixes add roughly another hour in the same session.

## Note on earlier bogus totals

The block table below and any “~10h / ~21h grand total” lines were **planned-effort estimates copied from the take-home brief**, not stopwatch time. They should not be cited as hours worked.

| Block (brief plan only) | Target |
|---|---|
| repo + schema | 30m |
| jobs + fixtures | 60m |
| blogs + github | 60m |
| query layer | 120m |
| Playwright + oracle | 120m |
| Cloak + HashiCorp | 15m |
| browser-use agent | 90m |
| UI | 45m |
| evals | 60m |
| docs | 60m |

## Review-fix commits (same session)

| Phase | Commits |
|---|---|
| V2 | RFC-822 dates, degraded ledger, expect_result evals, Q3 remote, Playwright diagnosis |
| V3 | date bounds, guard split, extractive fallback, exclusion counts, make test, timeline limit, rendered evals |
| V4 | topic keywords, scored compare retrieval, timeline caveat panel |
| V5 | ChatDeepSeek agent subprocess, a11y-tree DeepSeek, five-method oracle table |
| V6 | Agent schema diagnosis, trimmed action registry, ChatDeepSeekJSON path, oracle + cost basis |
