"""
Database layer: plain SQLAlchemy 2.x with a Flask-SQLAlchemy-style
compatibility surface.

The app started on Flask-SQLAlchemy; the FastAPI rewrite keeps every
model and every business module (project_memory, report, matching)
unchanged by providing the same namespace:

- ``db.Model``      -> DeclarativeBase whose models expose ``.query``
                       (via a metaclass property), so ``Risk.query...``
                       keeps working.
- ``db.Column`` ... -> plain re-exports of sqlalchemy constructs.
- ``db.session``   -> a scoped session: get/add/flush/commit/rollback/
                       scalar/query/remove, bound by configure_database.
- ``db.create_all()`` -> metadata create_all on the bound engine.

The engine binds late: configure_database(url) is called once by the
FastAPI app factory (live) or by the test suite (in-memory sqlite).
"""

import contextvars
import os
import uuid

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeMeta,
    declarative_base,
    relationship,
    scoped_session,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from config_loader import load_env


class _QueryMeta(DeclarativeMeta):
    """Give every model the classic ``Model.query`` property."""

    @property
    def query(cls):
        return _Session.query(cls)


# The classic query-shim recipe: the legacy declarative_base() accepts
# a custom metaclass, and every model keeps ``.query`` working.
Base = declarative_base(metaclass=_QueryMeta)


# Sessions scope per HTTP request: FastAPI runs sync endpoints in a
# threadpool, so plain thread-scoping would leak identity maps across
# requests on reused threads. A contextvar set by the request
# middleware gives every request its own session in any thread, and
# code outside requests (tests, scripts) shares the None scope.
_session_scope = contextvars.ContextVar("ada_session_scope", default=None)

_Session = scoped_session(
    # Same semantics as the Flask-SQLAlchemy session it replaces:
    # autoflush on, so add-then-query sees pending changes.
    sessionmaker(autoflush=True),
    scopefunc=lambda: _session_scope.get(),
)

engine = None


def configure_database(database_url=None):
    """
    Create the engine and bind the session factory to it.

    Reads DATABASE_URL from the environment (via the .env loader) when
    no explicit URL is given. Call once at startup or per test run.
    """
    global engine

    url = database_url

    if url is None:
        load_env()
        url = os.getenv("DATABASE_URL")

        if not url:
            raise RuntimeError(
                "DATABASE_URL is missing. "
                "Configure PostgreSQL before starting the app."
            )

    engine = create_engine(url, future=True)

    # In-memory sqlite (tests) must be one shared connection across the
    # FastAPI threadpool; the default per-thread pool would give every
    # worker thread its own empty database.
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    _Session.configure(bind=engine)
    return engine


def create_all():
    """Create every table on the bound engine (tests, fresh installs)."""
    if engine is None:
        raise RuntimeError("configure_database() must run before create_all().")

    Base.metadata.create_all(engine)


def drop_all():
    """Drop every table on the bound engine (test teardown)."""
    if engine is None:
        raise RuntimeError("configure_database() must run before drop_all().")

    Base.metadata.drop_all(engine)


def session_remove():
    """Drop the current thread's session (request teardown analogue)."""
    _Session.remove()


def new_request_scope():
    """Mark the start of an HTTP request: fresh session scope."""
    return _session_scope.set("request-" + uuid.uuid4().hex)


def close_request_scope(token):
    """
    End of an HTTP request: roll back any open transaction and drop
    the request's session, so identity maps never leak between
    requests. Call from the same context that set the token.
    """
    try:
        _Session.rollback()
    finally:
        _Session.remove()
        _session_scope.reset(token)


class _DB:
    """
    The compatibility namespace models and business modules import.

    ``from database import db`` keeps working, and so does every
    db.* construct those modules use.
    """

    Model = Base
    Column = Column
    # Functions bound through the _DB instance would swallow db as
    # their first positional argument (argument=), so wrap the plain
    # functions as staticmethods. Types such as Column/Integer bind
    # through class-attribute access unchanged and need no wrapper.
    relationship = staticmethod(relationship)
    Integer = Integer
    String = String
    Text = Text
    DateTime = DateTime
    JSON = JSON
    Date = Date
    ForeignKey = ForeignKey
    select = staticmethod(select)
    func = func

    create_all = staticmethod(create_all)
    drop_all = staticmethod(drop_all)

    class session:
        """Proxy to the scoped session, mirroring Flask-SQLAlchemy."""

        get = staticmethod(_Session.get)
        add = staticmethod(_Session.add)
        add_all = staticmethod(_Session.add_all)
        delete = staticmethod(_Session.delete)
        flush = staticmethod(_Session.flush)
        commit = staticmethod(_Session.commit)
        rollback = staticmethod(_Session.rollback)
        refresh = staticmethod(_Session.refresh)
        expire_all = staticmethod(_Session.expire_all)
        scalar = staticmethod(_Session.scalar)
        execute = staticmethod(_Session.execute)
        remove = staticmethod(_Session.remove)
        query = staticmethod(_Session.query)


db = _DB()
