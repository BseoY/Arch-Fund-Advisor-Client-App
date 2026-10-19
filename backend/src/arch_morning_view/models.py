import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class AdvisorSession(Model):
    token: str
    role: Literal["advisor"]
    name: str


class ClientSession(Model):
    token: str
    role: Literal["client"]
    name: str
    client_id: str


Session = Annotated[AdvisorSession | ClientSession, Field(discriminator="role")]


class Client(Model):
    id: str
    name: str


class Fund(Model):
    id: str
    client_id: str
    name: str


class CapitalCallInput(Model):
    kind: Literal["capital_call"]
    title: str
    amount: float
    due_date: str


class InvestorLetterInput(Model):
    kind: Literal["investor_letter"]
    title: str
    summary: str


DocumentInput = CapitalCallInput | InvestorLetterInput


class CapitalCall(CapitalCallInput):
    id: str
    fund_id: str
    created_at: datetime
    paid: bool
    checked: bool | None = None


class InvestorLetter(InvestorLetterInput):
    id: str
    fund_id: str
    created_at: datetime


FundDocument = Annotated[CapitalCall | InvestorLetter, Field(discriminator="kind")]


class FundWithDocuments(Fund):
    documents: list[FundDocument]


class MorningItem(Model):
    document_id: str
    fund_id: str
    fund_name: str
    title: str
    amount: float
    due_date: str


class ClientOverview(Model):
    client: Client
    morning: list[MorningItem]
    funds: list[FundWithDocuments]


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def require_name_password(body: Any) -> tuple[str, str]:
    if not isinstance(body, dict):
        raise APIError(400, "Name and password are required.")
    name = body.get("name")
    password = body.get("password")
    if not isinstance(name, str) or not name.strip() or not isinstance(password, str) or password == "":
        raise APIError(400, "Name and password are required.")
    return name.strip(), password


def login_name_password(body: Any) -> tuple[str, str]:
    if not isinstance(body, dict):
        raise APIError(401, "Wrong name or password.")
    name = body.get("name")
    password = body.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        raise APIError(401, "Wrong name or password.")
    return name.strip(), password


def require_fund_name(body: Any) -> str:
    if not isinstance(body, dict):
        raise APIError(400, "Fund name is required.")
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise APIError(400, "Fund name is required.")
    return name.strip()


def parse_document(body: Any) -> DocumentInput:
    if not isinstance(body, dict):
        raise APIError(400, "Unknown document type.")
    title = body.get("title")
    if not isinstance(title, str) or not title.strip():
        raise APIError(400, "A document needs a title.")
    title = title.strip()
    kind = body.get("kind")
    if kind == "capital_call":
        amount = body.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not amount > 0:
            raise APIError(400, "Amount due must be greater than zero.")
        due = body.get("dueDate")
        if not isinstance(due, str) or _DATE.fullmatch(due) is None:
            raise APIError(400, "Due date is required.")
        return CapitalCallInput(kind="capital_call", title=title, amount=float(amount), due_date=due)
    if kind == "investor_letter":
        summary = body.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise APIError(400, "An investor letter needs a summary.")
        return InvestorLetterInput(kind="investor_letter", title=title, summary=summary.strip())
    raise APIError(400, "Unknown document type.")
