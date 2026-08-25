"""browser-use discovery launcher — subprocess only, never imports browser-use."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

OUT_PATH = Path("fixtures/vercel_agent_discovery.json")
REPO = Path(__file__).resolve().parent
DEFAULT_BROWSER_USE_PYTHON = Path(
    "/Users/heman10x/Downloads/claude_dev/oss-repos/scraping-and-trends/browser-use/browser-use/.venv/bin/python"
)
AGENT_TIMEOUT_S = 90 * 60


def _write_trace(payload: dict) -> dict:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    return payload


def _browser_use_python() -> Path:
    return Path(os.environ.get("BROWSER_USE_PYTHON", str(DEFAULT_BROWSER_USE_PYTHON)))


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

    py = _browser_use_python()
    if not py.is_file():
        return _write_trace(
            {
                "status": "skipped",
                "reason": "browser-use venv python not found",
                "detail": str(py),
                "jobs": [],
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "steps": 0,
                "trace": f"Expected browser-use interpreter at {py}",
            }
        )

    worker = REPO / "agent_vercel_discovery.py"
    env = os.environ.copy()
    try:
        proc = subprocess.run(
            [str(py), str(worker)],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=AGENT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return _write_trace(
            {
                "status": "failed",
                "reason": "agent run timed out after 90 minutes",
                "jobs": [],
                "wall_clock_s": float(AGENT_TIMEOUT_S),
                "cost_usd": 0.0,
                "steps": 0,
                "trace": "Hard cap 90 minutes reached before agent finished.",
            }
        )
    except Exception as exc:
        return _write_trace(
            {
                "status": "failed",
                "reason": "agent subprocess failed to launch",
                "error": str(exc),
                "jobs": [],
                "wall_clock_s": 0.0,
                "cost_usd": 0.0,
                "steps": 0,
                "trace": str(exc),
            }
        )

    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text())

    return _write_trace(
        {
            "status": "failed",
            "reason": "agent run crashed",
            "error": proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}",
            "jobs": [],
            "wall_clock_s": 0.0,
            "cost_usd": 0.0,
            "steps": 0,
            "trace": (proc.stdout + "\n" + proc.stderr)[-15000:],
        }
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(run_discovery_tasks(), indent=2))
    sys.exit(0)
