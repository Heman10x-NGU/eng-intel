.PHONY: seed run ingest eval test browser-oracle browser-cloak

PYTHON ?= .venv/bin/python

install:
	/Users/heman10x/.local/bin/python3.11 -m venv .venv --upgrade-deps
	.venv/bin/pip install -r requirements.txt

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
