"""In-memory data for Arch Morning View.

Seeded accounts, so the frontend has something to show after sign-in:

- Advisor: Ada / password
- Client: Bea / password
- Client: Cal / password
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from arch_morning_view.auth import hash_password, new_token, verify_password
from arch_morning_view.models import (
    APIError,
    AdvisorSession,
    CapitalCall,
    Client,
    ClientOverview,
    ClientSession,
    DocumentInput,
    Fund,
    FundDocument,
    FundWithDocuments,
    InvestorLetter,
    MorningItem,
    Session,
    parse_document,
    require_fund_name,
    require_name_password,
)

SEED_ADVISOR_NAME = "Ada"
SEED_ADVISOR_PASSWORD = "password"
SEED_CLIENTS = (("Bea", "password"), ("Cal", "password"))


@dataclass
class UserRow:
    id: str
    role: str
    name: str
    salt: str
    password_hash: str
    client_id: str | None = None


@dataclass
class ClientRow:
    id: str
    name: str


@dataclass
class FundRow:
    id: str
    client_id: str
    name: str


@dataclass
class DocumentRow:
    id: str
    fund_id: str
    created_at: datetime
    kind: str
    title: str
    amount: float | None = None
    due_date: str | None = None
    summary: str | None = None
    paid: bool = False


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


class Store:
    def __init__(self) -> None:
        self._lock = RLock()
        self.users: list[UserRow] = []
        self.clients: list[ClientRow] = []
        self.funds: list[FundRow] = []
        self.documents: list[DocumentRow] = []
        self.checks: set[tuple[str, str]] = set()
        self.sessions: dict[str, str] = {}

    def reset(self) -> None:
        with self._lock:
            self._clear()

    def seed(self) -> None:
        with self._lock:
            self._clear()
            self._seed()

    def has_advisor(self) -> bool:
        with self._lock:
            return self._advisor_row() is not None

    def setup_advisor(self, body: dict) -> AdvisorSession:
        with self._lock:
            if self._advisor_row() is not None:
                raise APIError(409, "The advisor already exists.")
            name, password = require_name_password(body)
            user = self._add_user("advisor", name, password)
            session = self._start_session(user)
            assert isinstance(session, AdvisorSession)
            return session

    def login(self, name: str, password: str) -> Session:
        with self._lock:
            folded = name.casefold()
            user = next((u for u in self.users if u.name.casefold() == folded), None)
            if user is None or not verify_password(password, user.salt, user.password_hash):
                raise APIError(401, "Wrong name or password.")
            return self._start_session(user)

    def user_for_token(self, token: str) -> UserRow | None:
        with self._lock:
            user_id = self.sessions.get(token)
            if user_id is None:
                return None
            return self._find_user(user_id)

    def session_for_token(self, token: str) -> Session | None:
        with self._lock:
            user_id = self.sessions.get(token)
            user = self._find_user(user_id) if user_id else None
            if user is None:
                return None
            return self._session(user, token)

    def logout(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token, None)

    def list_clients(self, actor: UserRow) -> list[Client]:
        with self._lock:
            self._require_advisor(actor)
            rows = sorted(self.clients, key=lambda row: row.name.casefold())
            return [Client(id=row.id, name=row.name) for row in rows]

    def create_client(self, actor: UserRow, body: dict) -> Client:
        with self._lock:
            self._require_advisor(actor)
            name, password = require_name_password(body)
            return self._create_client(name, password)

    def update_client(self, actor: UserRow, client_id: str, body: dict) -> Client:
        with self._lock:
            self._require_advisor(actor)
            client = self._find_client(client_id)
            user = self._user_for_client(client_id)
            if client is None or user is None:
                raise APIError(404, "Client not found.")
            if "name" in body and body.get("name") is not None:
                raw = body.get("name")
                if not isinstance(raw, str) or not raw.strip():
                    raise APIError(400, "Name is required.")
                renamed = raw.strip()
                if self._name_taken(renamed, except_user_id=user.id):
                    raise APIError(409, "That name is already used.")
                client.name = renamed
                user.name = renamed
            password = body.get("password")
            if isinstance(password, str) and password:
                user.salt, user.password_hash = hash_password(password)
            return Client(id=client.id, name=client.name)

    def delete_client(self, actor: UserRow, client_id: str) -> None:
        with self._lock:
            self._require_advisor(actor)
            fund_ids = {row.id for row in self.funds if row.client_id == client_id}
            self._remove_documents({row.id for row in self.documents if row.fund_id in fund_ids})
            self.funds = [row for row in self.funds if row.client_id != client_id]
            user_ids = {row.id for row in self.users if row.client_id == client_id}
            self.users = [row for row in self.users if row.id not in user_ids]
            self.sessions = {token: user_id for token, user_id in self.sessions.items() if user_id not in user_ids}
            self.clients = [row for row in self.clients if row.id != client_id]

    def create_fund(self, actor: UserRow, client_id: str, body: dict) -> Fund:
        with self._lock:
            self._require_advisor(actor)
            if self._find_client(client_id) is None:
                raise APIError(404, "Client not found.")
            return self._add_fund(client_id, require_fund_name(body))

    def update_fund(self, actor: UserRow, fund_id: str, body: dict) -> Fund:
        with self._lock:
            self._require_advisor(actor)
            fund = self._require_fund(fund_id)
            fund.name = require_fund_name(body)
            return Fund(id=fund.id, client_id=fund.client_id, name=fund.name)

    def delete_fund(self, actor: UserRow, fund_id: str) -> None:
        with self._lock:
            self._require_advisor(actor)
            self._require_fund(fund_id)
            self._remove_documents({row.id for row in self.documents if row.fund_id == fund_id})
            self.funds = [row for row in self.funds if row.id != fund_id]

    def create_document(self, actor: UserRow, fund_id: str, body: dict) -> FundDocument:
        with self._lock:
            self._require_advisor(actor)
            self._require_fund(fund_id)
            incoming = parse_document(body)
            row = self._add_document(fund_id, incoming, datetime.now(timezone.utc), paid=False)
            return self._document_out(row, actor)

    def update_document(self, actor: UserRow, document_id: str, body: dict) -> FundDocument:
        with self._lock:
            self._require_advisor(actor)
            row = self._require_document(document_id)
            incoming = parse_document(body)
            row.kind = incoming.kind
            row.title = incoming.title
            if incoming.kind == "capital_call":
                row.amount = incoming.amount
                row.due_date = incoming.due_date
                row.summary = None
            else:
                row.summary = incoming.summary
                row.amount = None
                row.due_date = None
            return self._document_out(row, actor)

    def delete_document(self, actor: UserRow, document_id: str) -> None:
        with self._lock:
            self._require_advisor(actor)
            self._require_document(document_id)
            self._remove_documents({document_id})

    def set_paid(self, actor: UserRow, document_id: str, body: dict) -> None:
        with self._lock:
            self._require_advisor(actor)
            row = self._require_document(document_id)
            if row.kind != "capital_call":
                raise APIError(400, "Only capital calls can be paid.")
            if not isinstance(body, dict) or not isinstance(body.get("paid"), bool):
                raise APIError(400, "Paid status is required.")
            row.paid = body["paid"]

    def set_checked(self, actor: UserRow, document_id: str, body: dict) -> None:
        with self._lock:
            if actor.role != "client" or not actor.client_id:
                raise APIError(403, "Only a client can do that.")
            row = self._require_document(document_id)
            fund = self._find_fund(row.fund_id)
            if fund is None or fund.client_id != actor.client_id:
                raise APIError(404, "Document not found.")
            if not isinstance(body, dict) or not isinstance(body.get("checked"), bool):
                raise APIError(400, "Checked status is required.")
            key = (actor.client_id, document_id)
            self.checks.discard(key)
            if body["checked"]:
                self.checks.add(key)

    def overview(self, actor: UserRow, client_id: str) -> ClientOverview:
        with self._lock:
            if actor.role == "client" and actor.client_id != client_id:
                raise APIError(404, "Client not found.")
            client = self._find_client(client_id)
            if client is None:
                raise APIError(404, "Client not found.")
            funds = sorted(
                (row for row in self.funds if row.client_id == client_id),
                key=lambda row: row.name.casefold(),
            )
            morning: list[MorningItem] = []
            fund_views: list[FundWithDocuments] = []
            for fund in funds:
                documents = sorted(
                    (row for row in self.documents if row.fund_id == fund.id),
                    key=lambda row: row.created_at,
                    reverse=True,
                )
                views: list[FundDocument] = []
                for row in documents:
                    views.append(self._document_out(row, actor))
                    if row.kind == "capital_call" and not row.paid:
                        morning.append(
                            MorningItem(
                                document_id=row.id,
                                fund_id=fund.id,
                                fund_name=fund.name,
                                title=row.title,
                                amount=row.amount or 0,
                                due_date=row.due_date or "",
                            )
                        )
                fund_views.append(
                    FundWithDocuments(id=fund.id, client_id=fund.client_id, name=fund.name, documents=views)
                )
            morning.sort(key=lambda item: item.due_date)
            return ClientOverview(client=Client(id=client.id, name=client.name), morning=morning, funds=fund_views)

    def _clear(self) -> None:
        self.users = []
        self.clients = []
        self.funds = []
        self.documents = []
        self.checks = set()
        self.sessions = {}

    def _seed(self) -> None:
        self._add_user("advisor", SEED_ADVISOR_NAME, SEED_ADVISOR_PASSWORD)
        bea = self._create_client("Bea", "password")
        cal = self._create_client("Cal", "password")
        northwind = self._add_fund(bea.id, "Northwind Growth")
        harbor = self._add_fund(bea.id, "Harbor Credit")
        summit = self._add_fund(cal.id, "Summit Partners")
        q3 = self._add_document(
            northwind.id,
            _call("Q3 capital call", 250_000, "2026-11-01"),
            _utc(2026, 10, 2),
            paid=False,
        )
        self._add_document(
            northwind.id,
            _call("Q4 capital call", 500_000, "2026-12-15"),
            _utc(2026, 10, 18),
            paid=False,
        )
        self._add_document(
            northwind.id,
            _letter("Quarterly letter", "Two new portfolio companies and a partial exit."),
            _utc(2026, 10, 20),
            paid=False,
        )
        self._add_document(
            northwind.id,
            _call("Q2 capital call", 100_000, "2026-06-01"),
            _utc(2026, 6, 1),
            paid=True,
        )
        self._add_document(
            harbor.id,
            _call("October call", 75_000, "2026-11-20"),
            _utc(2026, 10, 5),
            paid=False,
        )
        self._add_document(
            summit.id,
            _call("Year-end call", 180_000, "2026-12-01"),
            _utc(2026, 10, 12),
            paid=False,
        )
        self._add_document(
            summit.id,
            _letter("Year in review", "The portfolio held up through a slow quarter."),
            _utc(2026, 10, 21),
            paid=False,
        )
        self.checks.add((bea.id, q3.id))

    def _advisor_row(self) -> UserRow | None:
        return next((row for row in self.users if row.role == "advisor"), None)

    def _require_advisor(self, actor: UserRow) -> None:
        if actor.role != "advisor":
            raise APIError(403, "Only the advisor can do that.")

    def _name_taken(self, name: str, except_user_id: str | None = None) -> bool:
        folded = name.casefold()
        return any(row.name.casefold() == folded and row.id != except_user_id for row in self.users)

    def _add_user(self, role: str, name: str, password: str, client_id: str | None = None) -> UserRow:
        salt, password_hash = hash_password(password)
        user = UserRow(
            id=str(uuid4()),
            role=role,
            name=name,
            salt=salt,
            password_hash=password_hash,
            client_id=client_id,
        )
        self.users.append(user)
        return user

    def _create_client(self, name: str, password: str) -> Client:
        if self._name_taken(name):
            raise APIError(409, "That name is already used.")
        client = ClientRow(id=str(uuid4()), name=name)
        self.clients.append(client)
        self._add_user("client", name, password, client_id=client.id)
        return Client(id=client.id, name=client.name)

    def _add_fund(self, client_id: str, name: str) -> Fund:
        fund = FundRow(id=str(uuid4()), client_id=client_id, name=name)
        self.funds.append(fund)
        return Fund(id=fund.id, client_id=fund.client_id, name=fund.name)

    def _add_document(self, fund_id: str, incoming: DocumentInput, created_at: datetime, paid: bool) -> DocumentRow:
        if incoming.kind == "capital_call":
            row = DocumentRow(
                id=str(uuid4()),
                fund_id=fund_id,
                created_at=created_at,
                kind="capital_call",
                title=incoming.title,
                amount=incoming.amount,
                due_date=incoming.due_date,
                paid=paid,
            )
        else:
            row = DocumentRow(
                id=str(uuid4()),
                fund_id=fund_id,
                created_at=created_at,
                kind="investor_letter",
                title=incoming.title,
                summary=incoming.summary,
                paid=False,
            )
        self.documents.append(row)
        return row

    def _start_session(self, user: UserRow) -> Session:
        token = new_token()
        self.sessions[token] = user.id
        return self._session(user, token)

    def _session(self, user: UserRow, token: str) -> Session:
        if user.role == "client":
            return ClientSession(token=token, role="client", name=user.name, client_id=user.client_id or "")
        return AdvisorSession(token=token, role="advisor", name=user.name)

    def _find_user(self, user_id: str) -> UserRow | None:
        return next((row for row in self.users if row.id == user_id), None)

    def _find_client(self, client_id: str) -> ClientRow | None:
        return next((row for row in self.clients if row.id == client_id), None)

    def _user_for_client(self, client_id: str) -> UserRow | None:
        return next((row for row in self.users if row.client_id == client_id), None)

    def _find_fund(self, fund_id: str) -> FundRow | None:
        return next((row for row in self.funds if row.id == fund_id), None)

    def _require_fund(self, fund_id: str) -> FundRow:
        fund = self._find_fund(fund_id)
        if fund is None:
            raise APIError(404, "Fund not found.")
        return fund

    def _require_document(self, document_id: str) -> DocumentRow:
        row = next((item for item in self.documents if item.id == document_id), None)
        if row is None:
            raise APIError(404, "Document not found.")
        return row

    def _remove_documents(self, ids: set[str]) -> None:
        if not ids:
            return
        self.documents = [row for row in self.documents if row.id not in ids]
        self.checks = {key for key in self.checks if key[1] not in ids}

    def _document_out(self, row: DocumentRow, viewer: UserRow) -> FundDocument:
        if row.kind == "capital_call":
            checked = None
            if viewer.role == "client" and viewer.client_id:
                checked = (viewer.client_id, row.id) in self.checks
            return CapitalCall(
                id=row.id,
                fund_id=row.fund_id,
                created_at=row.created_at,
                kind="capital_call",
                title=row.title,
                amount=row.amount or 0,
                due_date=row.due_date or "",
                paid=row.paid,
                checked=checked,
            )
        return InvestorLetter(
            id=row.id,
            fund_id=row.fund_id,
            created_at=row.created_at,
            kind="investor_letter",
            title=row.title,
            summary=row.summary or "",
        )


def _call(title: str, amount: float, due_date: str) -> DocumentInput:
    from arch_morning_view.models import CapitalCallInput

    return CapitalCallInput(kind="capital_call", title=title, amount=amount, due_date=due_date)


def _letter(title: str, summary: str) -> DocumentInput:
    from arch_morning_view.models import InvestorLetterInput

    return InvestorLetterInput(kind="investor_letter", title=title, summary=summary)


store = Store()
store.seed()
