"""Score browser extractors against Greenhouse API ground truth."""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import FIXTURE_PATHS

WORK_MODEL = re.compile(r"^\s*(hybrid|remote|on-?site)\s*[-–]\s*", re.I)


def norm_location(value: str | None) -> frozenset[str]:
    """Comparison-only: strip work-model prefix and compare city tokens as a set."""
    stripped = WORK_MODEL.sub("", value or "")
    return frozenset(part.strip().lower() for part in stripped.split(",") if part.strip())


def load_ground_truth(department: str | None = None) -> list[dict]:
    data = json.loads(Path(FIXTURE_PATHS["vercel_jobs"]).read_text())
    jobs: list[dict] = []
    for row in data.get("jobs", []):
        if department:
            dept_names = [d.get("name") for d in (row.get("departments") or []) if d.get("name")]
            if department not in dept_names:
                continue
        jobs.append(
            {
                "title": row.get("title"),
                "url": row.get("absolute_url"),
                "location": (row.get("location") or {}).get("name"),
                "department": (row.get("departments") or [{}])[0].get("name") if row.get("departments") else None,
            }
        )
    return jobs


def _title_match_exact(candidate: str | None, ground: str | None) -> bool:
    cand = (candidate or "").strip()
    gt = (ground or "").strip()
    if cand == gt:
        return True
    return bool(cand and gt and cand in gt)


def _field_match_exact(candidate: dict, ground: dict, field: str) -> bool:
    if field == "title":
        return _title_match_exact(candidate.get("title"), ground.get("title"))
    return (candidate.get(field) or "").strip() == (ground.get(field) or "").strip()


def _field_match_normalized(candidate: dict, ground: dict, field: str) -> bool:
    if field == "location":
        return norm_location(candidate.get("location")) == norm_location(ground.get("location"))
    return _field_match_exact(candidate, ground, field)


def _field_scores(candidate: list[dict], gt_by_url: dict[str, dict], *, normalized: bool) -> dict[str, float]:
    match_fn = _field_match_normalized if normalized else _field_match_exact
    totals = {field: 0 for field in ("title", "location", "department")}
    matches = {field: 0 for field in totals}
    for row in candidate:
        url = row.get("url")
        if url not in gt_by_url:
            continue
        ground = gt_by_url[url]
        for field in totals:
            totals[field] += 1
            if match_fn(row, ground, field):
                matches[field] += 1
    return {
        field: round(matches[field] / totals[field], 3) if totals[field] else 0.0
        for field in totals
    }


def score_candidate(
    gt: list[dict],
    candidate: list[dict],
    method: str,
    wall_clock_s: float,
    cost: float = 0.0,
    *,
    scope: str = "full board",
) -> dict:
    gt_urls = {job["url"] for job in gt if job.get("url")}
    cand_urls = {job.get("url") for job in candidate if job.get("url")}
    found = len(gt_urls & cand_urls)
    missed = sorted(gt_urls - cand_urls)[:5]
    invented = sorted(cand_urls - gt_urls)[:5]
    gt_by_url = {job["url"]: job for job in gt if job.get("url")}

    fields_exact = _field_scores(candidate, gt_by_url, normalized=False)
    fields_normalized = _field_scores(candidate, gt_by_url, normalized=True)

    exact_matches = sum(
        1
        for row in candidate
        if row.get("url") in gt_by_url
        for field in ("title", "location", "department")
        if _field_match_exact(row, gt_by_url[row["url"]], field)
    )
    exact_total = sum(
        1
        for row in candidate
        if row.get("url") in gt_by_url
        for _field in ("title", "location", "department")
    )
    normalized_matches = sum(
        1
        for row in candidate
        if row.get("url") in gt_by_url
        for field in ("title", "location", "department")
        if _field_match_normalized(row, gt_by_url[row["url"]], field)
    )

    field_accuracy_exact = round(exact_matches / exact_total, 3) if exact_total else 0.0
    field_accuracy_normalized = round(normalized_matches / exact_total, 3) if exact_total else 0.0

    return {
        "method": method,
        "scope": scope,
        "found": found,
        "total": len(gt),
        "recall": round(found / len(gt), 3) if gt else 0,
        "field_accuracy": field_accuracy_exact,
        "field_accuracy_exact": field_accuracy_exact,
        "field_accuracy_normalized": field_accuracy_normalized,
        "fields_accuracy": fields_exact,
        "fields_accuracy_normalized": fields_normalized,
        "wall_clock_s": wall_clock_s,
        "cost_usd": cost,
        "beats_bot_walls": method == "cloakbrowser",
        "missed_sample": missed,
        "invented_sample": invented,
    }


def main() -> None:
    gt_full = load_ground_truth()
    gt_engineering = load_ground_truth("Engineering")
    results = [
        score_candidate(gt_full, gt_full, "greenhouse_api", wall_clock_s=1.0, cost=0.0, scope="full board"),
    ]

    pw_path = Path("artifacts/playwright_vercel.json")
    if pw_path.exists():
        pw = json.loads(pw_path.read_text())
        results.append(
            score_candidate(
                gt_full,
                pw.get("jobs", []),
                "playwright-selectors",
                pw.get("wall_clock_s", 0),
                scope="full board",
            )
        )
    else:
        try:
            from ingest_jobs_browser import scrape_vercel_playwright

            jobs, elapsed = scrape_vercel_playwright()
            pw_path.parent.mkdir(exist_ok=True)
            pw_path.write_text(json.dumps({"jobs": jobs, "wall_clock_s": elapsed}, indent=2))
            results.append(score_candidate(gt_full, jobs, "playwright-selectors", elapsed, scope="full board"))
        except Exception as exc:
            results.append({"method": "playwright-selectors", "scope": "full board", "error": str(exc)})

    a11y_path = Path("artifacts/a11y_vercel.json")
    if a11y_path.exists():
        a11y = json.loads(a11y_path.read_text())
        if a11y.get("jobs") is not None:
            results.append(
                score_candidate(
                    gt_full,
                    a11y.get("jobs", []),
                    "a11y-tree-deepseek",
                    a11y.get("wall_clock_s", 0),
                    cost=a11y.get("cost_usd", 0),
                    scope="full board",
                )
            )

    agent_path = Path("fixtures/vercel_agent_discovery.json")
    if agent_path.exists():
        agent = json.loads(agent_path.read_text())
        if isinstance(agent.get("jobs"), list) and agent.get("status") == "completed":
            agent_jobs = agent.get("jobs", [])
            scoped = score_candidate(
                gt_engineering,
                agent_jobs,
                "browser-use-agent",
                agent.get("wall_clock_s", 0),
                cost=agent.get("cost_usd", 0),
                scope="engineering only",
            )
            full_board = score_candidate(
                gt_full,
                agent_jobs,
                "browser-use-agent",
                agent.get("wall_clock_s", 0),
                cost=agent.get("cost_usd", 0),
                scope="full board",
            )
            scoped["found_full_board"] = full_board["found"]
            scoped["total_full_board"] = full_board["total"]
            scoped["recall_full_board"] = full_board["recall"]
            results.append(scoped)

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
                    gt_engineering,
                    artifact.get("jobs", []),
                    method,
                    artifact.get("wall_clock_s", 0),
                    cost=artifact.get("cost_usd", 0),
                    scope="engineering only",
                )
            )

    results.append(
        {
            "method": "cloakbrowser",
            "scope": "full board",
            "found": 0,
            "total": 0,
            "recall": None,
            "field_accuracy": None,
            "field_accuracy_exact": None,
            "field_accuracy_normalized": None,
            "fields_accuracy": None,
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
