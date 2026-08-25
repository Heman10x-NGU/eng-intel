"""browser-use discovery — optional ingest-only, never imported by app."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

OUT_PATH = Path("fixtures/vercel_agent_discovery.json")

TASK = (
    "Start at vercel.com. Find where the company lists its open engineering roles, "
    "navigate to that listing, and extract every job you can see as JSON with fields: "
    "title, location, department, url. Return only the JSON array."
)


def _write_trace(payload: dict) -> dict:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    return payload


def _normalize_job_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("/"):
        url = urljoin("https://job-boards.greenhouse.io", url)
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def _parse_jobs_from_text(text: str) -> list[dict]:
    if not text:
        return []
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    jobs: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        jobs.append(
            {
                "title": item.get("title"),
                "location": item.get("location"),
                "department": item.get("department"),
                "url": _normalize_job_url(item.get("url")),
            }
        )
    return [j for j in jobs if j.get("url")]


async def _run_vercel_agent() -> dict:
    from browser_use import Agent
    from browser_use.llm import ChatDeepSeek

    llm = ChatDeepSeek(model="deepseek-v4-flash", api_key=os.environ["DEEPSEEK_API_KEY"])
    agent = Agent(
        task=TASK,
        llm=llm,
        use_vision=False,
        max_actions_per_step=3,
        calculate_cost=True,
    )
    history = await agent.run(max_steps=25)
    usage = history.usage
    cost = float(usage.total_cost) if usage else 0.0
    trace = history.final_result() or ""
    return {
        "jobs": _parse_jobs_from_text(trace),
        "wall_clock_s": 0.0,
        "cost_usd": cost,
        "steps": history.number_of_steps(),
        "trace": trace,
    }


def run_discovery_tasks() -> dict:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return _write_trace(
            {
                "status": "skipped",
                "reason": "DEEPSEEK_API_KEY not set",
                "jobs": [],
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "steps": 0,
                "trace": "Set DEEPSEEK_API_KEY in .env to run browser-use discovery.",
            }
        )

    try:
        import browser_use  # noqa: F401
    except ImportError as exc:
        return _write_trace(
            {
                "status": "skipped",
                "reason": "browser-use package not installed in this Python environment",
                "detail": str(exc),
                "jobs": [],
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "steps": 0,
                "trace": "Run via browser-use venv subprocess (see ingest_jobs_agent launcher).",
            }
        )

    t0 = time.time()
    try:
        result = asyncio.run(_run_vercel_agent())
        result["wall_clock_s"] = round(time.time() - t0, 2)
        result["status"] = "completed"
        return _write_trace(result)
    except Exception as exc:
        return _write_trace(
            {
                "status": "failed",
                "reason": "agent run crashed",
                "error": str(exc),
                "jobs": [],
                "wall_clock_s": round(time.time() - t0, 2),
                "cost_usd": 0.0,
                "steps": 0,
                "trace": str(exc),
            }
        )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(run_discovery_tasks(), indent=2))
