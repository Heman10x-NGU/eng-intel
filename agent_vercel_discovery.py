#!/usr/bin/env python3
"""browser-use worker — run only from the browser-use venv (Python 3.12)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parent
OUT_PATH = REPO / "fixtures" / "vercel_agent_discovery.json"

TASK = (
    "Start at vercel.com. Find where the company lists its open engineering roles, "
    "navigate to that listing, and extract every job you can see as JSON with fields: "
    "title, location, department, url. Return only the JSON array."
)

# DeepSeek V4 Flash off-peak (api-docs.deepseek.com, Aug 2026)
INPUT_MISS_PER_M = 0.22
INPUT_HIT_PER_M = 0.007
OUTPUT_PER_M = 0.66


def _write(payload: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))


def _normalize_job_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("/"):
        url = urljoin("https://job-boards.greenhouse.io", url)
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if "greenhouse.io" in url and "/jobs/" in url:
        return url.split("?")[0]
    return url


def _parse_jobs_from_text(text: str) -> list[dict]:
    if not text:
        return []
    for match in re.finditer(r"\[[\s\S]*?\]", text):
        try:
            raw = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, list):
            continue
        jobs: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = _normalize_job_url(item.get("url"))
            if not url:
                continue
            jobs.append(
                {
                    "title": item.get("title"),
                    "location": item.get("location"),
                    "department": item.get("department"),
                    "url": url,
                }
            )
        if jobs:
            return jobs
    return []


def _history_trace(history) -> str:
    parts: list[str] = []
    for step in history.history:
        if step.model_output and step.model_output.current_state:
            parts.append(f"step: {step.model_output.current_state}")
        for result in step.result or []:
            if result.extracted_content:
                parts.append(result.extracted_content)
            if result.error:
                parts.append(f"error: {result.error}")
    final = history.final_result()
    if final:
        parts.append(f"final: {final}")
    return "\n".join(parts)[-15000:]


def _cost_from_usage(usage) -> float:
    if usage and usage.total_cost > 0:
        return float(usage.total_cost)
    if not usage:
        return 0.0
    miss = usage.total_prompt_tokens - usage.total_prompt_cached_tokens
    hit = usage.total_prompt_cached_tokens
    return (
        miss * INPUT_MISS_PER_M / 1_000_000
        + hit * INPUT_HIT_PER_M / 1_000_000
        + usage.total_completion_tokens * OUTPUT_PER_M / 1_000_000
    )


async def _run() -> dict:
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
    trace = _history_trace(history)
    jobs = _parse_jobs_from_text(trace)
    usage = history.usage
    return {
        "status": "completed",
        "jobs": jobs,
        "steps": history.number_of_steps(),
        "trace": trace,
        "cost_usd": round(_cost_from_usage(usage), 6),
    }


def main() -> int:
    if not os.getenv("DEEPSEEK_API_KEY"):
        _write(
            {
                "status": "skipped",
                "reason": "DEEPSEEK_API_KEY not set",
                "jobs": [],
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "steps": 0,
                "trace": "DEEPSEEK_API_KEY missing in worker environment",
            }
        )
        return 1

    t0 = time.time()
    try:
        result = asyncio.run(_run())
        result["wall_clock_s"] = round(time.time() - t0, 2)
        _write(result)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        payload = {
            "status": "failed",
            "reason": "agent run crashed",
            "error": str(exc),
            "jobs": [],
            "wall_clock_s": round(time.time() - t0, 2),
            "cost_usd": 0.0,
            "steps": 0,
            "trace": str(exc),
        }
        _write(payload)
        print(json.dumps(payload, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
