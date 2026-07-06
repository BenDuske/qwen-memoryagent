# Aegis MemoryAgent — Qwen Cloud Hackathon (Track 1)
# One-command reproduce. `make verify` needs NO API key.

.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install test eval verify serve cli demo clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install package + keyless test deps (pytest, httpx) — runtime itself is stdlib-only
	$(PY) -m pip install -e ".[dev]"

test: ## Run the keyless test suite (95 tests; the 2 HTTP-service files skip)
	$(PY) -m pytest -q

eval: ## Quantify the memory engine (salience 8/8 vs naive 0/8)
	$(PY) eval.py

verify: install test eval ## Keyless end-to-end: install + tests + evaluation (no API key)
	@echo "VERIFY OK — tests green, salience budget beats naive recency."

serve: ## Run the FastAPI service face (memoryagent.app:app on :8000)
	$(PY) -m pip install -e ".[service]"
	$(PY) -m uvicorn memoryagent.app:app --port 8000

cli: ## Interactive CLI (needs QWEN_API_KEY in .env — proves cross-session recall)
	$(PY) -m memoryagent.cli

demo: ## Scripted live cross-session demo (needs QWEN_API_KEY in .env)
	$(PY) demo.py

clean: ## Remove caches and local scratch memory stores
	rm -rf .pytest_cache **/__pycache__ src/**/__pycache__ tests/__pycache__ .demo-mem .fgtest
