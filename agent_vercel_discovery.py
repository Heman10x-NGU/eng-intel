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
DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "deepseek-v4-flash")

TASK = (
    "Start at vercel.com. Find where the company lists its open engineering roles, "
    "navigate to that listing, and extract every job you can see as JSON with fields: "
    "title, location, department, url. Return only the JSON array."
)

# DeepSeek V4 Flash off-peak (api-docs.deepseek.com, Aug 2026)
INPUT_MISS_PER_M = 0.22
INPUT_HIT_PER_M = 0.007
OUTPUT_PER_M = 0.66


class ChatDeepSeekJSON:
    """Subclass ChatDeepSeek to bypass function-calling AgentOutput tool schema."""

    _token_usage: dict[str, int] = {"prompt": 0, "completion": 0, "cached": 0}

    @classmethod
    def _usage_from_response(cls, resp) -> object | None:
        from browser_use.llm.views import ChatInvokeUsage

        usage = getattr(resp, "usage", None)
        if not usage:
            return None
        cached = None
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", None)
        return ChatInvokeUsage(
            prompt_tokens=usage.prompt_tokens or 0,
            prompt_cached_tokens=cached,
            prompt_cache_creation_tokens=None,
            prompt_image_tokens=None,
            completion_tokens=usage.completion_tokens or 0,
            total_tokens=usage.total_tokens or 0,
        )

    @classmethod
    def _accumulate_usage(cls, usage) -> None:
        if not usage:
            return
        bucket = cls._token_usage
        bucket["prompt"] += usage.prompt_tokens or 0
        bucket["completion"] += usage.completion_tokens or 0
        bucket["cached"] += usage.prompt_cached_tokens or 0


def _install_chat_deepseek_json() -> type:
    import json

    from browser_use.llm.deepseek.chat import ChatDeepSeek
    from browser_use.llm.deepseek.serializer import DeepSeekMessageSerializer
    from browser_use.llm.messages import UserMessage
    from browser_use.llm.views import ChatInvokeCompletion

    if getattr(ChatDeepSeek, "_eng_intel_json_path", False):
        return ChatDeepSeek

    class _ChatDeepSeekJSON(ChatDeepSeek):
        async def ainvoke(
            self,
            messages,
            output_format=None,
            tools=None,
            stop=None,
            **kwargs,
        ):
            if output_format is None:
                return await super().ainvoke(messages, output_format, tools, stop, **kwargs)

            schema = output_format.model_json_schema()
            augmented = [
                *messages,
                UserMessage(
                    content=(
                        "Respond with a single JSON object matching this schema exactly. "
                        "The object MUST have an 'action' key containing a list. "
                        f"JSON schema: {json.dumps(schema)}"
                    )
                ),
            ]
            client = self._client()
            ds_messages = DeepSeekMessageSerializer.serialize_messages(augmented)
            common: dict = {}
            if self.temperature is not None:
                common["temperature"] = self.temperature
            if self.max_tokens is not None:
                common["max_tokens"] = self.max_tokens
            if self.top_p is not None:
                common["top_p"] = self.top_p
            if self.seed is not None:
                common["seed"] = self.seed
            extra_body = dict(kwargs.pop("extra_body", None) or {})
            extra_body.setdefault("thinking", {"type": "disabled"})
            resp = await client.chat.completions.create(
                model=self.model,
                messages=ds_messages,
                response_format={"type": "json_object"},
                extra_body=extra_body,
                **common,
            )
            content = resp.choices[0].message.content
            if not content:
                from browser_use.llm.exceptions import ModelProviderError

                raise ModelProviderError("Empty JSON content in DeepSeek response", model=self.name)
            parsed = output_format.model_validate_json(content)
            usage = ChatDeepSeekJSON._usage_from_response(resp)
            ChatDeepSeekJSON._accumulate_usage(usage)
            return ChatInvokeCompletion(completion=parsed, usage=usage)

    _ChatDeepSeekJSON._eng_intel_json_path = True
    return _ChatDeepSeekJSON


def _patch_deepseek_no_think() -> None:
    """DeepSeek V4 defaults to thinking mode, which rejects browser-use tool_choice."""
    from browser_use.llm.deepseek.chat import ChatDeepSeek

    if getattr(ChatDeepSeek, "_eng_intel_no_think", False):
        return

    original_client = ChatDeepSeek._client
    ChatDeepSeek._token_usage = {"prompt": 0, "completion": 0, "cached": 0}

    def _client_with_no_think(self):
        client = original_client(self)
        original_create = client.chat.completions.create

        async def create(*args, **kwargs):
            extra = dict(kwargs.pop("extra_body", None) or {})
            extra.setdefault("thinking", {"type": "disabled"})
            kwargs["extra_body"] = extra
            resp = await original_create(*args, **kwargs)
            usage = getattr(resp, "usage", None)
            if usage:
                bucket = ChatDeepSeek._token_usage
                bucket["prompt"] += usage.prompt_tokens or 0
                bucket["completion"] += usage.completion_tokens or 0
                cached = getattr(usage, "prompt_cache_hit_tokens", None)
                if cached is None:
                    cached = getattr(usage, "prompt_tokens_details", None)
                    if cached and hasattr(cached, "cached_tokens"):
                        cached = cached.cached_tokens
                bucket["cached"] += cached or 0
            return resp

        client.chat.completions.create = create
        return client

    ChatDeepSeek._client = _client_with_no_think
    ChatDeepSeek._eng_intel_no_think = True


def _cost_from_token_bucket() -> float:
    bucket = getattr(ChatDeepSeekJSON, "_token_usage", {})
    miss = max(bucket.get("prompt", 0) - bucket.get("cached", 0), 0)
    return (
        miss * INPUT_MISS_PER_M / 1_000_000
        + bucket.get("cached", 0) * INPUT_HIT_PER_M / 1_000_000
        + bucket.get("completion", 0) * OUTPUT_PER_M / 1_000_000
    )


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
    vercel_match = re.search(r"vercel\.com/careers/.+-(\d{8,})$", url)
    if vercel_match:
        return f"https://job-boards.greenhouse.io/vercel/jobs/{vercel_match.group(1)}"
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
        mo = step.model_output
        if mo is not None:
            parts.append(str(mo))
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


def _build_trimmed_tools():
    from browser_use.tools.service import Tools

    keep = {"navigate", "click", "input", "extract", "find_elements", "scroll", "done"}
    all_names = list(Tools().registry.registry.actions.keys())
    tools = Tools(exclude_actions=[n for n in all_names if n not in keep])
    count = len(tools.registry.registry.actions)
    assert count == 7, count
    return tools


async def _run() -> dict:
    from browser_use import Agent

    _patch_deepseek_no_think()
    llm_cls = _install_chat_deepseek_json()
    llm = llm_cls(model=DEFAULT_MODEL, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0)
    tools = _build_trimmed_tools()
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
    trace = _history_trace(history)
    jobs = _parse_jobs_from_text(trace)
    for job in jobs:
        job["url"] = _normalize_job_url(job.get("url"))
    jobs = [j for j in jobs if j.get("url") and "greenhouse.io" in j["url"]]
    usage = history.usage
    cost = float(usage.total_cost) if usage and usage.total_cost > 0 else _cost_from_token_bucket()
    if not cost and usage:
        cost = _cost_from_usage(usage)
    diagnosis = ""
    if not jobs:
        diagnosis = (
            "Model returned flat action JSON (e.g. {url, new_tab}) instead of "
            "browser-use's AgentOutput schema, causing consecutive pydantic validation "
            "failures. Root cause: action anyOf union collapse inside forced AgentOutput tool call."
        )
    return {
        "status": "completed" if jobs else "failed",
        "model": DEFAULT_MODEL,
        "jobs": jobs,
        "steps": history.number_of_steps(),
        "trace": trace,
        "diagnosis": diagnosis,
        "cost_usd": round(cost, 6),
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
