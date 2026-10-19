"""Persisted accounts, funds, documents, sessions, and checkmarks.

Seeded accounts, so the frontend has something to show after sign-in:

- Advisor: Ada / password
- Client: Bea / password
- Client: Cal / password
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from arch_morning_view.auth import hash_password, new_token, verify_password
from arch_morning_view.db import (
    AuthSession,
    CheckMark,
    ClientAccount,
    DocumentRecord,
    FundRecord,
    User,
    session_scope,
)
from arch_morning_view.models import (
    APIError,
    AdvisorSession,
    CapitalCall,
    CapitalCallInput,
    Client,
    ClientOverview,
    ClientSession,
    DocumentInput,
    Fund,
    FundDocument,
    FundWithDocuments,
    InvestorLetter,
    InvestorLetterInput,
    MorningItem,
    Session,
    parse_document,
    require_fund_name,
    require_name_password,
)

UserRow = User

SEED_ADVISOR_NAME = "Ada"
SEED_ADVISOR_PASSWORD = "password"


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class Store:
    def reset(self) -> None:
        with session_scope() as db:
            self._clear(db)

    def seed(self) -> None:
        with session_scope() as db:
            self._clear(db)
            self._seed(db)

    def seed_if_empty(self) -> None:
        with session_scope() as db:
            if self._advisor_row(db) is None:
                self._seed(db)

    def has_advisor(self) -> bool:
        with session_scope() as db:
            return self._advisor_row(db) is not None

    def setup_advisor(self, body: dict) -> AdvisorSession:
        with session_scope() as db:
            if self._advisor_row(db) is not None:
                raise APIError(409, "The advisor already exists.")
            name, password = require_name_password(body)
            user = self._add_user(db, "advisor", name, password)
            session = self._start_session(db, user)
            assert isinstance(session, AdvisorSession)
            return session

    def login(self, name: str, password: str) -> Session:
        with session_scope() as db:
            user = db.scalar(select(User).where(User.name_key == name.casefold()))
            if user is None or not verify_password(password, user.salt, user.password_hash):
                raise APIError(401, "Wrong name or password.")
            return self._start_session(db, user)

    def user_for_token(self, token: str) -> User | None:
        with session_scope() as db:
            auth = db.get(AuthSession, token)
            if auth is None:
                return None
            user = db.get(User, auth.user_id)
            if user is not None:
                db.expunge(user)
            return user

    def session_for_token(self, token: str) -> Session | None:
        with session_scope() as db:
            auth = db.get(AuthSession, token)
            user = db.get(User, auth.user_id) if auth else None
            if user is None:
                return None
            return self._session(user, token)

    def logout(self, token: str) -> None:
        with session_scope() as db:
            db.execute(delete(AuthSession).where(AuthSession.token == token))

    def list_clients(self, actor: User) -> list[Client]:
        with session_scope() as db:
            self._require_advisor(actor)
            rows = db.scalars(select(ClientAccount)).all()
            return [Client(id=row.id, name=row.name) for row in sorted(rows, key=lambda row: row.name.casefold())]

    def create_client(self, actor: User, body: dict) -> Client:
        with session_scope() as db:
            self._require_advisor(actor)
            name, password = require_name_password(body)
            return self._create_client(db, name, password)

    def update_client(self, actor: User, client_id: str, body: dict) -> Client:
        with session_scope() as db:
            self._require_advisor(actor)
            client = db.get(ClientAccount, client_id)
            user = db.scalar(select(User).where(User.client_id == client_id))
            if client is None or user is None:
                raise APIError(404, "Client not found.")
            if "name" in body and body.get("name") is not None:
                raw = body.get("name")
                if not isinstance(raw, str) or not raw.strip():
                    raise APIError(400, "Name is required.")
                renamed = raw.strip()
                if self._name_taken(db, renamed, except_user_id=user.id):
                    raise APIError(409, "That name is already used.")
                client.name = renamed
                user.name = renamed
                user.name_key = renamed.casefold()
            password = body.get("password")
            if isinstance(password, str) and password:
                user.salt, user.password_hash = hash_password(password)
            return Client(id=client.id, name=client.name)

    def delete_client(self, actor: User, client_id: str) -> None:
        with session_scope() as db:
            self._require_advisor(actor)
            fund_ids = set(db.scalars(select(FundRecord.id).where(FundRecord.client_id == client_id)).all())
            doc_ids = set(db.scalars(select(DocumentRecord.id).where(DocumentRecord.fund_id.in_(fund_ids))).all()) if fund_ids else set()
            self._remove_documents(db, doc_ids)
            db.execute(delete(FundRecord).where(FundRecord.client_id == client_id))
            user_ids = set(db.scalars(select(User.id).where(User.client_id == client_id)).all())
            if user_ids:
                db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
                db.execute(delete(User).where(User.id.in_(user_ids)))
            db.execute(delete(ClientAccount).where(ClientAccount.id == client_id))

    def create_fund(self, actor: User, client_id: str, body: dict) -> Fund:
        with session_scope() as db:
            self._require_advisor(actor)
            if db.get(ClientAccount, client_id) is None:
                raise APIError(404, "Client not found.")
            return self._add_fund(db, client_id, require_fund_name(body))

    def update_fund(self, actor: User, fund_id: str, body: dict) -> Fund:
        with session_scope() as db:
            self._require_advisor(actor)
            fund = self._require_fund(db, fund_id)
            fund.name = require_fund_name(body)
            return Fund(id=fund.id, client_id=fund.client_id, name=fund.name)

    def delete_fund(self, actor: User, fund_id: str) -> None:
        with session_scope() as db:
            self._require_advisor(actor)
            self._require_fund(db, fund_id)
            doc_ids = set(db.scalars(select(DocumentRecord.id).where(DocumentRecord.fund_id == fund_id)).all())
            self._remove_documents(db, doc_ids)
            db.execute(delete(FundRecord).where(FundRecord.id == fund_id))

    def create_document(self, actor: User, fund_id: str, body: dict) -> FundDocument:
        with session_scope() as db:
            self._require_advisor(actor)
            self._require_fund(db, fund_id)
            incoming = parse_document(body)
            row = self._add_document(db, fund_id, incoming, datetime.now(timezone.utc), paid=False)
            return self._document_out(db, row, actor)

    def update_document(self, actor: User, document_id: str, body: dict) -> FundDocument:
        with session_scope() as db:
            self._require_advisor(actor)
            row = self._require_document(db, document_id)
            incoming = parse_document(body)
            row.kind = incoming.kind
            row.title = incoming.title
            if isinstance(incoming, CapitalCallInput):
                row.amount = incoming.amount
                row.due_date = incoming.due_date
                row.summary = None
            else:
                row.summary = incoming.summary
                row.amount = None
                row.due_date = None
            return self._document_out(db, row, actor)

    def delete_document(self, actor: User, document_id: str) -> None:
        with session_scope() as db:
            self._require_advisor(actor)
            self._require_document(db, document_id)
            self._remove_documents(db, {document_id})

    def set_paid(self, actor: User, document_id: str, body: dict) -> None:
        with session_scope() as db:
            self._require_advisor(actor)
            row = self._require_document(db, document_id)
            if row.kind != "capital_call":
                raise APIError(400, "Only capital calls can be paid.")
            if not isinstance(body, dict) or not isinstance(body.get("paid"), bool):
                raise APIError(400, "Paid status is required.")
            row.paid = body["paid"]

    def set_checked(self, actor: User, document_id: str, body: dict) -> None:
        with session_scope() as db:
            if actor.role != "client" or not actor.client_id:
                raise APIError(403, "Only a client can do that.")
            row = self._require_document(db, document_id)
            fund = db.get(FundRecord, row.fund_id)
            if fund is None or fund.client_id != actor.client_id:
                raise APIError(404, "Document not found.")
            if not isinstance(body, dict) or not isinstance(body.get("checked"), bool):
                raise APIError(400, "Checked status is required.")
            key = db.get(CheckMark, (actor.client_id, document_id))
            if body["checked"]:
                if key is None:
                    db.add(CheckMark(client_id=actor.client_id, document_id=document_id))
            elif key is not None:
                db.delete(key)

    def overview(self, actor: User, client_id: str) -> ClientOverview:
        with session_scope() as db:
            if actor.role == "client" and actor.client_id != client_id:
                raise APIError(404, "Client not found.")
            client = db.get(ClientAccount, client_id)
            if client is None:
                raise APIError(404, "Client not found.")
            funds = sorted(
                db.scalars(select(FundRecord).where(FundRecord.client_id == client_id)).all(),
                key=lambda row: row.name.casefold(),
            )
            morning: list[MorningItem] = []
            fund_views: list[FundWithDocuments] = []
            for fund in funds:
                documents = sorted(
                    db.scalars(select(DocumentRecord).where(DocumentRecord.fund_id == fund.id)).all(),
                    key=lambda row: _aware(row.created_at),
                    reverse=True,
                )
                views: list[FundDocument] = []
                for row in documents:
                    views.append(self._document_out(db, row, actor))
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

    def _clear(self, db) -> None:
        db.execute(delete(CheckMark))
        db.execute(delete(AuthSession))
        db.execute(delete(DocumentRecord))
        db.execute(delete(FundRecord))
        db.execute(delete(User))
        db.execute(delete(ClientAccount))

    def _seed(self, db) -> None:
        self._add_user(db, "advisor", SEED_ADVISOR_NAME, SEED_ADVISOR_PASSWORD)
        bea = self._create_client(db, "Bea", "password")
        cal = self._create_client(db, "Cal", "password")
        northwind = self._add_fund(db, bea.id, "Northwind Growth")
        harbor = self._add_fund(db, bea.id, "Harbor Credit")
        summit = self._add_fund(db, cal.id, "Summit Partners")
        q3 = self._add_document(db, northwind.id, _call("Q3 capital call", 250_000, "2026-11-01"), _utc(2026, 10, 2), paid=False)
        self._add_document(db, northwind.id, _call("Q4 capital call", 500_000, "2026-12-15"), _utc(2026, 10, 18), paid=False)
        self._add_document(
            db,
            northwind.id,
            _letter("Quarterly letter", "Two new portfolio companies and a partial exit."),
            _utc(2026, 10, 20),
            paid=False,
        )
        self._add_document(db, northwind.id, _call("Q2 capital call", 100_000, "2026-06-01"), _utc(2026, 6, 1), paid=True)
        self._add_document(db, harbor.id, _call("October call", 75_000, "2026-11-20"), _utc(2026, 10, 5), paid=False)
        self._add_document(db, summit.id, _call("Year-end call", 180_000, "2026-12-01"), _utc(2026, 10, 12), paid=False)
        self._add_document(
            db,
            summit.id,
            _letter("Year in review", "The portfolio held up through a slow quarter."),
            _utc(2026, 10, 21),
            paid=False,
        )
        db.add(CheckMark(client_id=bea.id, document_id=q3.id))

    def _advisor_row(self, db) -> User | None:
        return db.scalar(select(User).where(User.role == "advisor"))

    def _require_advisor(self, actor: User) -> None:
        if actor.role != "advisor":
            raise APIError(403, "Only the advisor can do that.")

    def _name_taken(self, db, name: str, except_user_id: str | None = None) -> bool:
        user = db.scalar(select(User).where(User.name_key == name.casefold()))
        return user is not None and user.id != except_user_id

    def _add_user(self, db, role: str, name: str, password: str, client_id: str | None = None) -> User:
        salt, password_hash = hash_password(password)
        user = User(
            id=str(uuid4()),
            role=role,
            name=name,
            name_key=name.casefold(),
            salt=salt,
            password_hash=password_hash,
            client_id=client_id,
        )
        db.add(user)
        db.flush()
        return user

    def _create_client(self, db, name: str, password: str) -> Client:
        if self._name_taken(db, name):
            raise APIError(409, "That name is already used.")
        client = ClientAccount(id=str(uuid4()), name=name)
        db.add(client)
        db.flush()
        self._add_user(db, "client", name, password, client_id=client.id)
        return Client(id=client.id, name=client.name)

    def _add_fund(self, db, client_id: str, name: str) -> Fund:
        fund = FundRecord(id=str(uuid4()), client_id=client_id, name=name)
        db.add(fund)
        db.flush()
        return Fund(id=fund.id, client_id=fund.client_id, name=fund.name)

    def _add_document(self, db, fund_id: str, incoming: DocumentInput, created_at: datetime, paid: bool) -> DocumentRecord:
        if isinstance(incoming, CapitalCallInput):
            row = DocumentRecord(
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
            row = DocumentRecord(
                id=str(uuid4()),
                fund_id=fund_id,
                created_at=created_at,
                kind="investor_letter",
                title=incoming.title,
                summary=incoming.summary,
                paid=False,
            )
        db.add(row)
        db.flush()
        return row

    def _start_session(self, db, user: User) -> Session:
        token = new_token()
        db.add(AuthSession(token=token, user_id=user.id))
        return self._session(user, token)

    def _session(self, user: User, token: str) -> Session:
        if user.role == "client":
            return ClientSession(token=token, role="client", name=user.name, client_id=user.client_id or "")
        return AdvisorSession(token=token, role="advisor", name=user.name)

    def _require_fund(self, db, fund_id: str) -> FundRecord:
        fund = db.get(FundRecord, fund_id)
        if fund is None:
            raise APIError(404, "Fund not found.")
        return fund

    def _require_document(self, db, document_id: str) -> DocumentRecord:
        row = db.get(DocumentRecord, document_id)
        if row is None:
            raise APIError(404, "Document not found.")
        return row

    def _remove_documents(self, db, ids: set[str]) -> None:
        if not ids:
            return
        db.execute(delete(CheckMark).where(CheckMark.document_id.in_(ids)))
        db.execute(delete(DocumentRecord).where(DocumentRecord.id.in_(ids)))

    def _document_out(self, db, row: DocumentRecord, viewer: User) -> FundDocument:
        created_at = _aware(row.created_at)
        if row.kind == "capital_call":
            checked = None
            if viewer.role == "client" and viewer.client_id:
                checked = db.get(CheckMark, (viewer.client_id, row.id)) is not None
            return CapitalCall(
                id=row.id,
                fund_id=row.fund_id,
                created_at=created_at,
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
            created_at=created_at,
            kind="investor_letter",
            title=row.title,
            summary=row.summary or "",
        )


def _call(title: str, amount: float, due_date: str) -> CapitalCallInput:
    return CapitalCallInput(kind="capital_call", title=title, amount=amount, due_date=due_date)


def _letter(title: str, summary: str) -> InvestorLetterInput:
    return InvestorLetterInput(kind="investor_letter", title=title, summary=summary)


store = Store()
