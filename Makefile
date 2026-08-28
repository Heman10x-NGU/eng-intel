.PHONY: seed run ingest eval test browser-oracle browser-cloak

PYTHON ?= .venv/bin/python
# Override if python3.11 is not on PATH: make install PYTHON311=/path/to/python3.11
PYTHON311 ?= python3.11

install:
	$(PYTHON311) -m venv .venv --upgrade-deps
	.venv/bin/pip install -r requirements.txt
	.venv/bin/playwright install chromium

seed:
	rm -f data.db
	INGEST_LIVE=0 $(PYTHON) seed.py

run:
	$(PYTHON) -m uvicorn app:app --host 127.0.0.1 --port 8000

ingest:
	INGEST_LIVE=1 $(PYTHON) seed.py

eval:
	$(PYTHON) evals/run_evals.py

test:
	PYTHONPATH=. $(PYTHON) -m unittest discover -s tests -v

browser-oracle:
	$(PYTHON) oracle.py

browser-cloak:
	$(PYTHON) ingest_jobs_browser.py --hashicorp

browser-a11y:
	set -a && [ -f .env ] && . ./.env; set +a && $(PYTHON) ingest_jobs_browser.py --a11y

browser-agent:
	set -a && [ -f .env ] && . ./.env; set +a && $(PYTHON) ingest_jobs_agent.py
