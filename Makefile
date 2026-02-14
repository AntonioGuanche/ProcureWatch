.PHONY: test test-unit test-cov lint check frontend

# ── Tests ────────────────────────────────────────────────────────────

test:
	python -m pytest tests/ -x -v --tb=short

test-unit:
	python -m pytest tests/ -m "not slow and not integration" -x -v --tb=short

test-cov:
	python -m pytest tests/ -m "not slow and not integration" \
		--cov=app --cov-report=term-missing --cov-report=html -x -v

test-file:
	@echo "Usage: make test-file F=tests/test_search.py"
	python -m pytest $(F) -x -v --tb=long

# ── Lint / check ─────────────────────────────────────────────────────

lint:
	python -m py_compile app/main.py
	python -m py_compile app/services/search_service.py
	python -m py_compile app/services/bulk_import.py
	python -m py_compile app/services/watchlist_matcher.py
	@echo "All core files compile OK"

check: lint test-unit

# ── Frontend ─────────────────────────────────────────────────────────

frontend:
	cd web && npm run build

frontend-dev:
	cd web && npm run dev
