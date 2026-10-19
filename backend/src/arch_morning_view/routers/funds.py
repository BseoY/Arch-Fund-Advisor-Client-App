from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response

from arch_morning_view.auth import get_current_user
from arch_morning_view.models import Fund
from arch_morning_view.store import UserRow, store

router = APIRouter(tags=["Funds"])


@router.post("/clients/{clientId}/funds", status_code=201)
def create_fund(
    clientId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Fund:
    return store.create_fund(user, clientId, body)


@router.patch("/funds/{fundId}")
def update_fund(
    fundId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Fund:
    return store.update_fund(user, fundId, body)


@router.delete("/funds/{fundId}", status_code=204)
def delete_fund(fundId: str, user: Annotated[UserRow, Depends(get_current_user)]) -> Response:
    store.delete_fund(user, fundId)
    return Response(status_code=204)
