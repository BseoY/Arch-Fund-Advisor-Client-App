from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from arch_morning_view.db import init_db
from arch_morning_view.models import APIError
from arch_morning_view.routers import clients, documents, funds, session
from arch_morning_view.store import store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    store.seed_if_empty()
    yield


app = FastAPI(title="Arch Morning View", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(session.router)
app.include_router(clients.router)
app.include_router(funds.router)
app.include_router(documents.router)


@app.exception_handler(APIError)
def api_error(_request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
