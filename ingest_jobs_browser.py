"""Playwright selector scrape (Vercel) + CloakBrowser (HashiCorp). Scored by oracle."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from config import ENDPOINTS, FIXTURE_PATHS

# DeepSeek V4 Flash off-peak USD per 1M tokens (api-docs.deepseek.com, Aug 2026)
_DEEPSEEK_INPUT_MISS = 0.22
_DEEPSEEK_INPUT_HIT = 0.007
_DEEPSEEK_OUTPUT = 0.66


SELECTORS = {
    "vercel": {
        "department_header": "h3",
        "job_row": "tr.job-post",
        "title": ".body--medium",
        "location": ".body--metadata",
        "job_link": 'a[href*="/jobs/"]',
    }
}


def scrape_vercel_playwright(headless: bool = True) -> tuple[list[dict], float]:
    from playwright.sync_api import sync_playwright

    url = ENDPOINTS["vercel"]["jobs_board"]
    t0 = time.time()
    jobs_by_url: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=90000)
        for dept in page.locator(SELECTORS["vercel"]["department_header"]).all():
            department = (dept.inner_text() or "").strip().split("\n")[0]
            rows = dept.evaluate(
                """(el) => {
                  const out = [];
                  let n = el.nextElementSibling;
                  while (n && n.tagName !== 'H3') {
                    n.querySelectorAll('tr.job-post').forEach((row) => {
                      const a = row.querySelector('a[href*="/jobs/"]');
                      const title = row.querySelector('.body--medium')?.textContent?.trim();
                      const loc = row.querySelector('.body--metadata')?.textContent?.trim();
                      if (a) out.push({ url: a.href, title, location: loc });
                    });
                    n = n.nextElementSibling;
                  }
                  return out;
                }"""
            )
            for row in rows:
                jobs_by_url[row["url"]] = {
                    "title": row.get("title"),
                    "url": row["url"],
                    "location": row.get("location"),
                    "department": department,
                }
        browser.close()
    return list(jobs_by_url.values()), time.time() - t0


def scrape_hashicorp_cloak() -> tuple[list[dict], float]:
    """CloakBrowser stealth scrape — proven against bot wall."""
    t0 = time.time()
    try:
        from cloakbrowser import launch
    except ImportError as exc:
        raise SystemExit(
            "cloakbrowser is not installed. Install with: pip install '.[browser]'"
        ) from exc
    try:
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


def _deepseek_cost(usage: dict) -> float:
    prompt = usage.get("prompt_tokens", 0)
    cached = usage.get("prompt_cache_hit_tokens") or usage.get("prompt_cached_tokens") or 0
    completion = usage.get("completion_tokens", 0)
    miss = max(prompt - cached, 0)
    return (
        miss * _DEEPSEEK_INPUT_MISS / 1_000_000
        + cached * _DEEPSEEK_INPUT_HIT / 1_000_000
        + completion * _DEEPSEEK_OUTPUT / 1_000_000
    )


def _deepseek_extract_jobs(tree_text: str) -> tuple[list[dict], float]:
    from agent_vercel_discovery import _parse_jobs_from_text

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    prompt = (
        "Extract every job posting from this accessibility tree as a JSON array. "
        "Each object must have: title, location, department, url. "
        "URLs must be absolute https://job-boards.greenhouse.io/vercel/jobs/... links. "
        "Return only the JSON array.\n\n"
        f"{tree_text[:120000]}"
    )
    resp = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "thinking": {"type": "disabled"},
        },
        timeout=180.0,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    cost = _deepseek_cost(data.get("usage") or {})
    return _parse_jobs_from_text(content), cost


def scrape_vercel_a11y(headless: bool = True) -> tuple[list[dict], float, float]:
    """Accessibility-tree extraction via aria_snapshot + DeepSeek JSON parse."""
    from playwright.sync_api import sync_playwright

    url = ENDPOINTS["vercel"]["jobs_board"]
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=90000)
        container = page.locator("#main, main, [role='main']").first
        if container.count() == 0:
            container = page.locator("body")
        tree = container.aria_snapshot()
        browser.close()

    jobs, cost = _deepseek_extract_jobs(tree)
    return jobs, time.time() - t0, cost


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vercel", action="store_true")
    parser.add_argument("--hashicorp", action="store_true")
    parser.add_argument("--a11y", action="store_true")
    args = parser.parse_args()

    out: dict = {}
    if args.a11y:
        jobs, elapsed, cost = scrape_vercel_a11y()
        payload = {
            "jobs": jobs,
            "wall_clock_s": round(elapsed, 2),
            "cost_usd": round(cost, 6),
            "found": len(jobs),
        }
        Path("artifacts/a11y_vercel.json").parent.mkdir(exist_ok=True)
        Path("artifacts/a11y_vercel.json").write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload, indent=2))
        return

    if args.vercel or (not args.hashicorp and not args.a11y):
        jobs, elapsed = scrape_vercel_playwright()
        out["playwright"] = {"jobs": jobs, "wall_clock_s": round(elapsed, 2), "found": len(jobs)}
        Path("artifacts/playwright_vercel.json").write_text(json.dumps(out["playwright"], indent=2))

    if args.hashicorp:
        jobs, elapsed = scrape_hashicorp_cloak()
        out["cloak"] = {"jobs": jobs, "wall_clock_s": round(elapsed, 2), "found": len(jobs)}
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
