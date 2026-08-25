"""Grounding guard — strip unbacked URLs and integers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GuardResult:
    text: str
    stripped_urls: list[str]
    stripped_numbers: list[str]


def _collect_allowed_urls(citations: list[dict]) -> set[str]:
    return {c.get("url", "") for c in citations if c.get("url")}


def _collect_allowed_numbers(rows: list[dict], aggregates: dict) -> set[str]:
    nums: set[str] = set()
    for k, v in aggregates.items():
        if isinstance(v, (int, float)):
            nums.add(str(int(v)) if float(v).is_integer() else str(v))
        elif isinstance(v, dict):
            for vv in v.values():
                if isinstance(vv, (int, float)):
                    nums.add(str(int(vv)))
    for row in rows:
        for v in row.values():
            if isinstance(v, (int, float)):
                nums.add(str(int(v)) if float(v).is_integer() else str(v))
    return nums


def apply_guard(answer: str, citations: list[dict], rows: list[dict], aggregates: dict) -> GuardResult:
    allowed_urls = _collect_allowed_urls(citations)
    allowed_nums = _collect_allowed_numbers(rows, aggregates)

    stripped_urls: list[str] = []
    stripped_numbers: list[str] = []

    def url_repl(m: re.Match) -> str:
        url = m.group(0)
        if url in allowed_urls:
            return url
        stripped_urls.append(url)
        return "[url removed]"

    text = re.sub(r"https?://[^\s\])>]+", url_repl, answer)

    def num_repl(m: re.Match) -> str:
        num = m.group(0)
        if num in allowed_nums:
            return num
        stripped_numbers.append(num)
        return "[n removed]"

    text = re.sub(r"\b\d+\b", num_repl, text)

    return GuardResult(text=text, stripped_urls=stripped_urls, stripped_numbers=stripped_numbers)
