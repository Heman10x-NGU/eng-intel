# HashiCorp careers — source notes

Field-tested against hashicorp.com and ibm.com on 2026-08-25, re-probed 2026-08-29.

---

## What the wall actually blocks

The careers URL returns **429** to clients that do not run JavaScript. Any real browser clears it — including stock Playwright Chromium with zero stealth. CloakBrowser is still a legitimate tool and remains the method of record; it was not *required* for the checkpoint.

Reproduced 2026-08-29 (`artifacts/v10_botwall_probe.json`):

| Client | JavaScript | Result |
|---|---|---|
| `curl` (browser User-Agent) | no | **429** — title `Vercel Security Checkpoint`; checkpoint HTML present |
| Stock Playwright Chromium, **headless**, no stealth | yes | **Search jobs \| IBM Careers** — `ibm.com/careers/search?q=hashicorp`; no checkpoint in HTML |
| Stock Playwright Chromium, **headed**, no stealth | yes | same as headless |
| CloakBrowser stealth, headless | yes | same IBM landing (prior scrape + V9 CDP Playwright client) |

**Use a browser for careers** (not `curl`/`httpx`). Do not use a browser for RSS, GitHub, or ATS JSON endpoints. The real obstacle is the IBM redirect, not the checkpoint.

Tested endpoints (unchanged):

| Endpoint | Method | Status | Evidence |
|---|---|---|---|
| `hashicorp.com/careers/open-positions` | HTTP GET | **429** | `Vercel Security Checkpoint` HTML |
| `boards-api.greenhouse.io/.../hashicorp` | HTTP GET | **404** | No Greenhouse board |
| `api.ashbyhq.com/.../hashicorp` | HTTP GET | **404** | No Ashby board |
| `hashicorp.com/blog/feed.xml` | HTTP GET | **200** | RSS works; **20 items** only |

---

## What is behind the wall

After checkpoint clearance, the careers URL **redirects** to:

`https://www.ibm.com/careers/search?q=hashicorp`

Result: **3 IBM Consulting roles** whose descriptions mention "hashicorp" — not HashiCorp-owned postings.

Sample titles (extracted to `fixtures/hashicorp_jobs_raw.json`):

- Senior Red Hat Architect, Hybrid Cloud and Data, IBM Consulting Federal
- AWS Cloud Full Stack Engineer - eSC or eDV Clearance required
- Senior Front End Developer - eSC or eDV Clearance Required

---

## Decision

1. Run CloakBrowser extractor (proves browser tier works).
2. Write raw rows to `fixtures/hashicorp_jobs_raw.json` for inspection.
3. Insert **zero** rows into `documents` for HashiCorp jobs.
4. Log `ingest_runs` with `n_rows=0`, `truncated=1`, note explaining IBM redirect.

Rationale: indexing IBM Consulting clearance roles as HashiCorp jobs would pollute Rust counts and remote-engineering filters.

---

## Blog feed caveat

`hashicorp.com/blog/feed.xml` returns only **20 entries** back to **2026-06-25**. Any cross-company ranking over 6 months must intersect coverage windows via `ingest_runs`.

---

## Agent discovery — CDP bridge (2026-08-29)

Tried driving CloakBrowser from browser-use over Chrome DevTools Protocol (**CDP**) — the wire protocol a debugger uses to control Chromium — because browser-use has no stealth flag of its own.

1. CloakBrowser launched with `--remote-debugging-port=9333`. `http://127.0.0.1:9333/json/version` returned a live `webSocketDebuggerUrl`.
2. Playwright `connect_over_cdp` to that port navigated `hashicorp.com/careers/open-positions` and landed on **Search jobs | IBM Careers** (`ibm.com/careers/search?q=hashicorp`). The wall is still clearable over CDP.
3. `browser_use.Browser(cdp_url="http://127.0.0.1:9333")` did **not** hold the session: the CDP websocket closed immediately, browser-use entered a reconnect loop, and `start()` / `navigate_to()` never returned (killed after minutes; `asyncio.wait_for` did not recover).

**Conclusion:** attaching browser-use's session manager over CDP fights CloakBrowser's own CDP ownership. That is a real composition limit. It is **not** a blocker for HashiCorp discovery: stock Chromium clears the JS challenge, so the agent can launch its own browser (see V10). Probe scripts: `scripts/v9_cloak_cdp_launch.py`, `scripts/v9_cdp_attach_probe.py`. Result: `artifacts/v9_cdp_probe.json`.

---

## Agent discovery — own Chromium, no CDP (2026-08-29)

Task: *"Find HashiCorp's current open job postings. Start at hashicorp.com. Report what you find, including where the trail leads and whether the postings are genuinely HashiCorp roles."*

browser-use launched its own stock Chromium (no CloakBrowser, no `cdp_url`). **25 steps**, **111.27s**, **$0.051357** (DeepSeek API `usage` at V4 off-peak rates). Narrative only — no structured job rows, so no oracle score.

Agent conclusion (verbatim): HashiCorp careers / Open positions redirect to IBM careers; a HashiCorp search returned three IBM postings (Senior Red Hat Architect, AWS Cloud Full Stack Engineer, Senior Front End Developer); the first is an IBM Consulting Federal role that mentions Terraform/Vault, not a HashiCorp-owned role; no genuine HashiCorp postings found.

That matches the CloakBrowser scrape: same dead end, two independent methods, **zero rows** inserted. Trace: `fixtures/hashicorp_agent_discovery.json`.
