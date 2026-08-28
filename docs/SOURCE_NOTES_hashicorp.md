# HashiCorp careers — source notes

Field-tested against hashicorp.com and ibm.com on 2026-08-25.
All endpoints probed via HTTP and CloakBrowser stealth Chromium.

---

## Anti-bot verdict: browser required for careers page

**Plain `httpx`/`curl` returns HTTP 429** on the careers URL with a Vercel Security Checkpoint body.

Tested endpoints:

| Endpoint | Method | Status | Evidence |
|---|---|---|---|
| `hashicorp.com/careers/open-positions` | HTTP GET | **429** | `Vercel Security Checkpoint` HTML |
| `boards-api.greenhouse.io/.../hashicorp` | HTTP GET | **404** | No Greenhouse board |
| `api.ashbyhq.com/.../hashicorp` | HTTP GET | **404** | No Ashby board |
| `hashicorp.com/blog/feed.xml` | HTTP GET | **200** | RSS works; **20 items** only |
| `hashicorp.com/careers/open-positions` | CloakBrowser headless + humanize | **200** | ~274KB DOM after ~10s |

**Use CloakBrowser for careers only.** Do not use it for RSS, GitHub, or ATS JSON endpoints.

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

**Conclusion:** attaching browser-use's session manager over CDP fights CloakBrowser's own CDP ownership. The stealth patches survive a Playwright CDP client; they do not survive (or cannot be used by) the browser-use agent loop. CloakBrowser remains the HashiCorp method of record. Probe scripts: `scripts/v9_cloak_cdp_launch.py`, `scripts/v9_cdp_attach_probe.py`. Result: `artifacts/v9_cdp_probe.json`. No agent discovery run, zero job rows inserted.
