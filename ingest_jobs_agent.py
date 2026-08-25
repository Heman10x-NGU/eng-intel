"""browser-use discovery tasks — optional ingest-only, never imported by app."""

from __future__ import annotations

import json
import os
from pathlib import Path


def run_discovery_tasks() -> dict:
    """Run agent discovery if browser-use and API key are available."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        trace = {
            "status": "skipped",
            "reason": "ANTHROPIC_API_KEY not set",
            "tasks": [
                "Start at vercel.com, find engineering roles, extract JSON",
                "Find HashiCorp current open job postings",
            ],
        }
        Path("fixtures/vercel_agent_discovery.json").write_text(json.dumps(trace, indent=2))
        Path("fixtures/hashicorp_agent_trace.json").write_text(json.dumps(trace, indent=2))
        return trace

    try:
        # Optional dependency — not in core requirements
        from browser_use import Agent  # type: ignore
        from langchain_anthropic import ChatAnthropic  # type: ignore

        llm = ChatAnthropic(model="claude-3-5-haiku-latest", temperature=0)
        agent = Agent(task="Find HashiCorp current open job postings starting from hashicorp.com", llm=llm)
        result = agent.run()
        trace = {"status": "completed", "result": str(result)}
        Path("fixtures/hashicorp_agent_trace.json").write_text(json.dumps(trace, indent=2, default=str))
        return trace
    except ImportError:
        trace = {"status": "skipped", "reason": "browser-use optional group not installed"}
        Path("fixtures/hashicorp_agent_trace.json").write_text(json.dumps(trace, indent=2))
        return trace
    except Exception as exc:
        trace = {"status": "failed", "error": str(exc)}
        Path("fixtures/hashicorp_agent_trace.json").write_text(json.dumps(trace, indent=2))
        return trace


if __name__ == "__main__":
    print(json.dumps(run_discovery_tasks(), indent=2))
