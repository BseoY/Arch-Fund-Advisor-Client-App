from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from arch_morning_view.models import APIError
from arch_morning_view.routers import clients, documents, funds, session

app = FastAPI(title="Arch Morning View", version="0.1.0")
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
