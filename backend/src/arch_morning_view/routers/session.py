from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from arch_morning_view.auth import get_bearer_token
from arch_morning_view.models import Session, login_name_password
from arch_morning_view.store import store

router = APIRouter(tags=["Session"])


@router.get("/advisor")
def has_advisor() -> bool:
    return store.has_advisor()


@router.post("/advisor", status_code=201)
def setup_advisor(body: Annotated[dict, Body()]) -> Session:
    return store.setup_advisor(body)


@router.post("/login")
def login(body: Annotated[dict, Body()]) -> Session:
    name, password = login_name_password(body)
    return store.login(name, password)


@router.get("/session")
def get_session(token: Annotated[str | None, Depends(get_bearer_token)]) -> Session | None:
    if token is None:
        return None
    return store.session_for_token(token)


@router.post("/logout", status_code=204)
def logout(token: Annotated[str | None, Depends(get_bearer_token)]) -> Response:
    if token is None:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    store.logout(token)
    return Response(status_code=204)
