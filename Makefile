.PHONY: run test

run:
	cd backend && uv run uvicorn arch_morning_view.app:app --reload --port 8000

test:
	cd backend && uv run pytest
