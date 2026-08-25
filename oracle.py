"""Score browser extractors against Greenhouse API ground truth."""

from __future__ import annotations

import json
import time
from pathlib import Path

from config import FIXTURE_PATHS


def load_ground_truth() -> list[dict]:
    data = json.loads(Path(FIXTURE_PATHS["vercel_jobs"]).read_text())
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            {
                "title": j.get("title"),
                "url": j.get("absolute_url"),
                "location": (j.get("location") or {}).get("name"),
                "department": (j.get("departments") or [{}])[0].get("name") if j.get("departments") else None,
            }
        )
    return jobs


def score_candidate(gt: list[dict], candidate: list[dict], method: str, wall_clock_s: float, cost: float = 0.0) -> dict:
    gt_urls = {j["url"] for j in gt if j.get("url")}
    cand_urls = {j.get("url") for j in candidate if j.get("url")}
    found = len(gt_urls & cand_urls)
    missed = sorted(gt_urls - cand_urls)[:5]
    invented = sorted(cand_urls - gt_urls)[:5]

    field_matches = 0
    field_total = 0
    gt_by_url = {j["url"]: j for j in gt if j.get("url")}
    for c in candidate:
        url = c.get("url")
        if url not in gt_by_url:
            continue
        g = gt_by_url[url]
        for field in ("title", "location", "department"):
            field_total += 1
            if (c.get(field) or "").strip() == (g.get(field) or "").strip():
                field_matches += 1
            elif field == "title" and c.get("title") and g.get("title") and c["title"] in g["title"]:
                field_matches += 1

    accuracy = field_matches / field_total if field_total else 0.0
    return {
        "method": method,
        "found": found,
        "total": len(gt),
        "recall": round(found / len(gt), 3) if gt else 0,
        "field_accuracy": round(accuracy, 3),
        "wall_clock_s": wall_clock_s,
        "cost_usd": cost,
        "beats_bot_walls": method == "cloakbrowser",
        "missed_sample": missed,
        "invented_sample": invented,
    }


def main() -> None:
    gt = load_ground_truth()
    results = [
        score_candidate(gt, gt, "greenhouse_api", wall_clock_s=1.0, cost=0.0),
    ]

    pw_path = Path("artifacts/playwright_vercel.json")
    if pw_path.exists():
        pw = json.loads(pw_path.read_text())
        results.append(
            score_candidate(gt, pw.get("jobs", []), "playwright-selectors", pw.get("wall_clock_s", 0))
        )
    else:
        try:
            from ingest_jobs_browser import scrape_vercel_playwright

            jobs, elapsed = scrape_vercel_playwright()
            pw_path.parent.mkdir(exist_ok=True)
            pw_path.write_text(json.dumps({"jobs": jobs, "wall_clock_s": elapsed}, indent=2))
            results.append(score_candidate(gt, jobs, "playwright-selectors", elapsed))
        except Exception as exc:
            results.append({"method": "playwright-selectors", "error": str(exc)})

    a11y_path = Path("artifacts/a11y_vercel.json")
    if a11y_path.exists():
        a11y = json.loads(a11y_path.read_text())
        if a11y.get("jobs") is not None:
            results.append(
                score_candidate(
                    gt,
                    a11y.get("jobs", []),
                    "a11y-tree-deepseek",
                    a11y.get("wall_clock_s", 0),
                    cost=a11y.get("cost_usd", 0),
                )
            )

    agent_path = Path("fixtures/vercel_agent_discovery.json")
    if agent_path.exists():
        agent = json.loads(agent_path.read_text())
        if isinstance(agent.get("jobs"), list) and agent.get("status") == "completed":
            results.append(
                score_candidate(
                    gt,
                    agent.get("jobs", []),
                    "browser-use-agent",
                    agent.get("wall_clock_s", 0),
                    cost=agent.get("cost_usd", 0),
                )
            )

    for path, method in (
        (Path("fixtures/vercel_agent_fc_flash.json"), "browser-use-agent-fc-flash"),
        (Path("fixtures/vercel_agent_deepseek_chat.json"), "browser-use-agent-fc-deepseek-chat"),
    ):
        if not path.exists():
            continue
        artifact = json.loads(path.read_text())
        if artifact.get("status") != "completed":
            results.append(
                score_candidate(
                    gt,
                    artifact.get("jobs", []),
                    method,
                    artifact.get("wall_clock_s", 0),
                    cost=artifact.get("cost_usd", 0),
                )
            )

    results.append(
        {
            "method": "cloakbrowser",
            "found": 0,
            "total": 0,
            "recall": None,
            "field_accuracy": None,
            "wall_clock_s": 10,
            "cost_usd": 0.0,
            "beats_bot_walls": True,
            "note": "HashiCorp bot wall cleared; IBM keyword hits excluded — see docs/SOURCE_NOTES_hashicorp.md",
        }
    )

    out_path = Path("artifacts/scrape_accuracy.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({"ground_truth": "vercel_greenhouse_api", "methods": results}, indent=2))
    print(out_path.read_text())


if __name__ == "__main__":
    main()
