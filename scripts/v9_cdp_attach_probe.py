"""Attach browser-use to CloakBrowser CDP and navigate HashiCorp careers.

Run from the browser-use venv.
"""

from __future__ import annotations

import asyncio
import json
import sys

CDP_URL = "http://127.0.0.1:9333"
TARGET = "https://www.hashicorp.com/careers/open-positions"


async def probe() -> dict:
    from browser_use import Browser

    browser = Browser(cdp_url=CDP_URL, keep_alive=True)
    await asyncio.wait_for(browser.start(), timeout=30)
    await asyncio.wait_for(browser.navigate_to(TARGET), timeout=45)
    await asyncio.sleep(8)
    title = await browser.get_current_page_title()
    final_url = await browser.get_current_page_url()
    return {"title": title, "final_url": final_url, "cdp_url": CDP_URL, "target": TARGET, "via": "browser_use.Browser"}


def main() -> int:
    try:
        result = asyncio.run(probe())
    except Exception as exc:
        payload = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(payload, indent=2))
        return 1
    title = result["title"] or ""
    if "IBM Careers" in title:
        result["gate"] = "pass"
        result["status"] = "ok"
    elif "Security Checkpoint" in title:
        result["gate"] = "fail"
        result["status"] = "checkpoint"
    else:
        result["gate"] = "unknown"
        result["status"] = "ok"
    print(json.dumps(result, indent=2))
    return 0 if result.get("gate") != "fail" else 2


if __name__ == "__main__":
    sys.exit(main())
