#!/usr/bin/env python3
"""HashiCorp discovery worker — browser-use venv; launches its own Chromium (no CDP)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import agent_vercel_discovery as vercel

REPO = Path(__file__).resolve().parent
OUT_PATH = REPO / "fixtures" / "hashicorp_agent_discovery.json"

TASK = (
    "Find HashiCorp's current open job postings. Start at hashicorp.com. Report what you find, "
    "including where the trail leads and whether the postings are genuinely HashiCorp roles."
)


def _write(payload: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))


async def _run() -> dict:
    from browser_use import Agent

    vercel.ChatDeepSeekJSON._token_usage = {"prompt": 0, "completion": 0, "cached": 0}
    vercel._patch_deepseek_no_think()
    llm_cls = vercel._install_chat_deepseek_json()
    llm = llm_cls(model=vercel.DEFAULT_MODEL, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0)
    tools = vercel._build_trimmed_tools()
    agent = Agent(
        task=TASK,
        llm=llm,
        tools=tools,
        use_vision=False,
        use_thinking=False,
        max_actions_per_step=1,
        calculate_cost=True,
        directly_open_url=False,
        enable_planning=False,
    )
    history = await agent.run(max_steps=25)
    trace = vercel._history_trace(history)
    usage = history.usage
    cost = float(usage.total_cost) if usage and usage.total_cost > 0 else vercel._cost_from_token_bucket()
    if not cost and usage:
        cost = vercel._cost_from_usage(usage)
    conclusion = (history.final_result() or "").strip()
    if not conclusion:
        conclusion = (trace or "")[-2000:]
    ok = bool(conclusion) and history.number_of_steps() > 0
    return {
        "status": "completed" if ok else "failed",
        "model": vercel.DEFAULT_MODEL,
        "steps": history.number_of_steps(),
        "cost_usd": round(cost, 6),
        "trace": trace,
        "conclusion": conclusion,
    }


def main() -> int:
    if not os.getenv("DEEPSEEK_API_KEY"):
        _write(
            {
                "status": "skipped",
                "reason": "DEEPSEEK_API_KEY not set",
                "steps": 0,
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "trace": "",
                "conclusion": "",
            }
        )
        return 1

    t0 = time.time()
    try:
        result = asyncio.run(_run())
        result["wall_clock_s"] = round(time.time() - t0, 2)
        _write(result)
        print(json.dumps({k: result[k] for k in ("status", "steps", "wall_clock_s", "cost_usd", "conclusion")}, indent=2))
        return 0
    except Exception as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
            "steps": 0,
            "wall_clock_s": round(time.time() - t0, 2),
            "cost_usd": 0.0,
            "trace": str(exc),
            "conclusion": "",
        }
        _write(payload)
        print(json.dumps(payload, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
