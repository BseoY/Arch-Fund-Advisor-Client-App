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

## Scope

Build only what `docs/SPEC.md` describes. An archive of deleted records is later work, not this MVP.

## Rules

- Login is a name and password. Names are unique.
- The advisor’s paid status is the only status that changes the morning list.
- A client’s checkmark is stored for that client and is never returned to the advisor.
- A client request can only read or update that client’s own funds and documents.
- Deleting a client deletes that login, its funds, and those funds’ documents. Deleting a fund deletes its documents.
