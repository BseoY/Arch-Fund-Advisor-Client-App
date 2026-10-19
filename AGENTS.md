# AGENTS.md

Working rules for Arch Morning View.

## Read first

- `docs/SPEC.md` is the product scope.
- `openapi.yaml` is the API contract. The backend and the frontend both follow it.

## Layout

- `backend/` — FastAPI application
- `frontend/` — React application
- `docs/` — supporting documentation
- `openapi.yaml` — HTTP API

## Stack

React, FastAPI, and SQLite. Passwords are stored hashed. The server is the source of truth for accounts, funds, documents, paid status, and each client’s checkmark.

## Backend

From the repository root, `make run` starts the API and `make test` runs the backend tests. From `backend/`, use uv:

```
uv sync
uv add <PACKAGE-NAME>
uv run python <PYTHON-FILE>
uv run pytest
uv run uvicorn arch_morning_view.app:app --reload --port 8000
```

The API is split into `routers`, `models`, `store`, `auth`, and `db`. SQLAlchemy connects with `DATABASE_URL`. The default is `sqlite:///arch.sqlite3`. Another database, such as Postgres, is the same models with a different URL and driver. An empty database is seeded on startup. Passwords are hashed. Protected routes use a bearer token.

## Git

Commit completed work. Do not push unless asked.

## Scope

Build only what `docs/SPEC.md` describes. An archive of deleted records is later work, not this MVP.

## Rules

- Login is a name and password. Names are unique.
- The advisor’s paid status is the only status that changes the morning list.
- A client’s checkmark is stored for that client and is never returned to the advisor.
- A client request can only read or update that client’s own funds and documents.
- Deleting a client deletes that login, its funds, and those funds’ documents. Deleting a fund deletes its documents.
