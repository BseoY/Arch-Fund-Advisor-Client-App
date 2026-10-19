from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response

from arch_morning_view.auth import get_current_user
from arch_morning_view.models import Client, ClientOverview
from arch_morning_view.store import UserRow, store

router = APIRouter(tags=["Clients"])


@router.get("/clients")
def list_clients(user: Annotated[UserRow, Depends(get_current_user)]) -> list[Client]:
    return store.list_clients(user)


@router.post("/clients", status_code=201)
def create_client(body: Annotated[dict, Body()], user: Annotated[UserRow, Depends(get_current_user)]) -> Client:
    return store.create_client(user, body)


@router.get("/clients/{clientId}", response_model_exclude_none=True)
def get_client_overview(clientId: str, user: Annotated[UserRow, Depends(get_current_user)]) -> ClientOverview:
    return store.overview(user, clientId)


@router.patch("/clients/{clientId}")
def update_client(
    clientId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Client:
    return store.update_client(user, clientId, body)


@router.delete("/clients/{clientId}", status_code=204)
def delete_client(clientId: str, user: Annotated[UserRow, Depends(get_current_user)]) -> Response:
    store.delete_client(user, clientId)
    return Response(status_code=204)
