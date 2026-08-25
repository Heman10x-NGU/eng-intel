"""Playwright selector scrape (Vercel) + CloakBrowser (HashiCorp). Scored by oracle."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from config import ENDPOINTS, FIXTURE_PATHS


SELECTORS = {
    "vercel": {
        "job_card": "a[href*='/jobs/']",
        "title": "a[href*='/jobs/']",
    }
}


def scrape_vercel_playwright(headless: bool = True) -> tuple[list[dict], float]:
    from playwright.sync_api import sync_playwright

    url = ENDPOINTS["vercel"]["jobs_board"]
    t0 = time.time()
    jobs: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        cards = page.query_selector_all(SELECTORS["vercel"]["job_card"])
        seen = set()
        for card in cards:
            href = card.get_attribute("href") or ""
            if "/jobs/" not in href:
                continue
            if not href.startswith("http"):
                href = "https://job-boards.greenhouse.io" + href
            if href in seen:
                continue
            seen.add(href)
            title = (card.inner_text() or "").strip().split("\n")[0]
            jobs.append(
                {
                    "title": title,
                    "url": href,
                    "location": None,
                    "department": None,
                }
            )
        browser.close()
    return jobs, time.time() - t0


def scrape_hashicorp_cloak() -> tuple[list[dict], float]:
    """CloakBrowser stealth scrape — proven against bot wall."""
    t0 = time.time()
    try:
        from cloakbrowser import launch

        browser = launch(headless=True, humanize=True)
        page = browser.new_page()
        page.goto(ENDPOINTS["hashicorp"]["careers_url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(10000)
        final_url = page.url
        text = page.content()
        browser.close()
        raw = {
            "source_url": ENDPOINTS["hashicorp"]["careers_url"],
            "redirect_url": final_url,
            "dom_bytes": len(text),
            "method": "cloakbrowser",
        }
        Path(FIXTURE_PATHS["hashicorp_jobs_raw"]).write_text(json.dumps(raw, indent=2))
        return [], time.time() - t0
    except Exception as exc:
        raw = json.loads(Path(FIXTURE_PATHS["hashicorp_jobs_raw"]).read_text())
        raw["error"] = str(exc)
        return raw.get("jobs", []), time.time() - t0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vercel", action="store_true")
    parser.add_argument("--hashicorp", action="store_true")
    args = parser.parse_args()

    out: dict = {}
    if args.vercel or not args.hashicorp:
        jobs, elapsed = scrape_vercel_playwright()
        out["playwright"] = {"jobs": jobs, "wall_clock_s": round(elapsed, 2), "found": len(jobs)}
        Path("artifacts/playwright_vercel.json").write_text(json.dumps(out["playwright"], indent=2))

    if args.hashicorp:
        jobs, elapsed = scrape_hashicorp_cloak()
        out["cloak"] = {"jobs": jobs, "wall_clock_s": round(elapsed, 2), "found": len(jobs)}
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
