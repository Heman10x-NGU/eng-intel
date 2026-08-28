"""Launch CloakBrowser with a CDP debug port. Run from ~/.cloak-venv/bin/python."""

from __future__ import annotations

import sys
import time

PORT = 9333


def main() -> int:
    from cloakbrowser import launch

    print(f"launching CloakBrowser with --remote-debugging-port={PORT}", flush=True)
    _browser = launch(
        headless=True,
        humanize=True,
        args=[f"--remote-debugging-port={PORT}"],
    )
    print("cloak launched; holding process for CDP attach", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
