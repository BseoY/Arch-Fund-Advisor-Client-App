"""Database connection. The URL comes from DATABASE_URL.

SQLite is the default. A Postgres URL works with the same models once its
driver is installed, for example postgresql+psycopg://user:pass@localhost/arch.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite:///arch.sqlite3"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    pass


class ClientAccount(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(255), unique=True)
    salt: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(128))
    client_id: Mapped[str | None] = mapped_column(String(36))


class FundRecord(Base):
    __tablename__ = "funds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(255))


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fund_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)


class AuthSession(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))


class CheckMark(Base):
    __tablename__ = "checks"

    client_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        url = make_url(database_url())
        kwargs: dict = {}
        if url.drivername.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if url.database in (None, ":memory:"):
                kwargs["poolclass"] = StaticPool
        _engine = create_engine(url, **kwargs)
        if url.drivername.startswith("sqlite"):
            event.listen(_engine, "connect", _enable_sqlite_foreign_keys)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    get_engine()
    assert _session_factory is not None
    db = _session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
