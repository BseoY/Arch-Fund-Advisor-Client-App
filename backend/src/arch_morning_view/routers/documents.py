from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response

from arch_morning_view.auth import get_current_user
from arch_morning_view.models import FundDocument
from arch_morning_view.store import UserRow, store

router = APIRouter(tags=["Documents"])


@router.post("/funds/{fundId}/documents", status_code=201, response_model_exclude_none=True)
def create_document(
    fundId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> FundDocument:
    return store.create_document(user, fundId, body)


@router.put("/documents/{documentId}", response_model_exclude_none=True)
def update_document(
    documentId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> FundDocument:
    return store.update_document(user, documentId, body)


@router.delete("/documents/{documentId}", status_code=204)
def delete_document(documentId: str, user: Annotated[UserRow, Depends(get_current_user)]) -> Response:
    store.delete_document(user, documentId)
    return Response(status_code=204)


@router.patch("/documents/{documentId}/paid", status_code=204)
def set_paid(
    documentId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Response:
    store.set_paid(user, documentId, body)
    return Response(status_code=204)


@router.patch("/documents/{documentId}/checked", status_code=204)
def set_checked(
    documentId: str,
    body: Annotated[dict, Body()],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> Response:
    store.set_checked(user, documentId, body)
    return Response(status_code=204)
