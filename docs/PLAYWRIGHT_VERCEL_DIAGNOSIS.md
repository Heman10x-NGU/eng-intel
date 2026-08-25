# Playwright Vercel board — measured failure diagnosis

**Date:** 2026-08-26  
**Board:** `https://job-boards.greenhouse.io/vercel`  
**Ground truth:** Greenhouse JSON API (`artifacts/scrape_accuracy.json`)

## Path chosen

**Acceptable negative result with diagnosis** — not silent 30% field accuracy.

We improved selectors to fix field extraction, then measured again. Recall stays at **50/87** because of a **Greenhouse embed server-side cap**, not lazy-loading we failed to scroll.

## Root causes (reproduced)

### 1. Field accuracy 30% → fixed (~97%)

| Before | After |
|---|---|
| Selector `a[href*='/jobs/']` grabbed link text blobs | `tr.job-post` rows with `.body--medium` (title) and `.body--metadata` (location) |
| `location` and `department` always `null` | Location from metadata; department from preceding `h3` header |

Oracle after fix: **field_accuracy 0.967** on matched rows.

### 2. Recall 57.5% — structural embed limit

| Observation | Evidence |
|---|---|
| Scroll does not increase job count | 15 scroll iterations: 50 → 50 links |
| No pagination / “load more” control | Page text search: no load-more UI |
| SSR HTML contains exactly 50 unique `/jobs/{id}` URLs | `len(set(re.findall(...))) == 50` while API returns **87** |
| Department `h3` headers present (9 visible) | Walking sibling DOM under each header still yields **50 total** |

**Conclusion:** The Greenhouse **embedded board** ships 50 jobs in the initial HTML. The remaining 37 jobs exist in the public JSON API but are **not present in the DOM** this scraper can access without calling that API (which would defeat the purpose of measuring browser extraction).

Missed job IDs are consistently from departments whose rows are omitted from the embed batch (sample in `scrape_accuracy.json` `missed_sample`).

## What would fix recall (>0.95)

1. **Use the API for ingest** (already done) — instant, exact.
2. **Browser path:** hit `boards-api.greenhouse.io` from Playwright `page.request.get()` — hybrid, not pure selector scrape.
3. **Per-job detail pages** — 87 sequential navigations; slow, brittle, still not “one board page”.

For this take-home, the honest story is: **selectors are now correct on what the embed exposes; the embed does not expose the full board.**

## Updated numbers

See `artifacts/scrape_accuracy.json` after `make browser-oracle`.
