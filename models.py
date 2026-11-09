"""
SQLAlchemy 2.0 declarative models (plain SQLAlchemy; no Flask anywhere).

The Mapped[...] annotations are what let a type checker see real types on
an instance. Under the legacy db.Column spelling mypy could only infer
the ORM descriptor, which made every query call in the app look like a
type error.
"""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped

from database import db


def utcnow():
    return datetime.now(UTC)


class Project(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "projects"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    name: Mapped[str] = db.mapped_column(String(200), unique=True)
    description: Mapped[str] = db.mapped_column(Text, default="")
    created_at: Mapped[datetime] = db.mapped_column(db.DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = db.mapped_column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    state: Mapped["ProjectState"] = db.relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    meetings: Mapped[list["Meeting"]] = db.relationship(
        back_populates="project", order_by="Meeting.created_at.desc()"
    )


class ProjectState(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "project_states"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), unique=True)
    delivery_status: Mapped[str] = db.mapped_column(String(20), default="unknown")
    progress_summary: Mapped[str] = db.mapped_column(Text, default="")
    completed_items: Mapped[Any] = db.mapped_column(db.JSON, default=list)
    in_progress_items: Mapped[Any] = db.mapped_column(db.JSON, default=list)
    updated_at: Mapped[datetime] = db.mapped_column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_in_meeting_id: Mapped[int | None] = db.mapped_column(ForeignKey("meetings.id"))

    project: Mapped["Project"] = db.relationship(back_populates="state")


class Meeting(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "meetings"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = db.mapped_column(String(250))
    source_filename: Mapped[str | None] = db.mapped_column(String(255))
    original_text: Mapped[str] = db.mapped_column(Text)
    analysis_text: Mapped[str] = db.mapped_column(Text)
    analysis_json: Mapped[Any] = db.mapped_column(db.JSON)
    provider: Mapped[str] = db.mapped_column(String(30))
    model: Mapped[str] = db.mapped_column(String(120))
    created_at: Mapped[datetime] = db.mapped_column(db.DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = db.relationship(back_populates="meetings")


class Risk(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "risks"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = db.mapped_column(String(300))
    canonical_title: Mapped[str] = db.mapped_column(String(300), default="")
    # JSON blob: embeddings are dynamic, so Any is the honest type.
    title_embedding: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    description: Mapped[str] = db.mapped_column(Text, default="")
    impact: Mapped[str] = db.mapped_column(String(20), default="unknown")
    mitigation: Mapped[str] = db.mapped_column(Text, default="")
    status: Mapped[str] = db.mapped_column(String(20), default="open", index=True)
    created_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    updated_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    resolved_in_meeting_id: Mapped[int | None] = db.mapped_column(ForeignKey("meetings.id"))
    resolved_at: Mapped[datetime | None] = db.mapped_column(db.DateTime(timezone=True))


class ActionItem(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "action_items"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = db.mapped_column(String(300))
    canonical_title: Mapped[str] = db.mapped_column(String(300), default="")
    title_embedding: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    details: Mapped[str] = db.mapped_column(Text, default="")
    owner: Mapped[str | None] = db.mapped_column(String(160))
    due_date: Mapped[date | None] = db.mapped_column(db.Date)
    status: Mapped[str] = db.mapped_column(String(20), default="open", index=True)
    created_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    updated_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    completed_in_meeting_id: Mapped[int | None] = db.mapped_column(ForeignKey("meetings.id"))
    completed_at: Mapped[datetime | None] = db.mapped_column(db.DateTime(timezone=True))


class Blocker(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "blockers"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = db.mapped_column(String(300))
    canonical_title: Mapped[str] = db.mapped_column(String(300), default="")
    title_embedding: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    description: Mapped[str] = db.mapped_column(Text, default="")
    status: Mapped[str] = db.mapped_column(String(20), default="open", index=True)
    created_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    updated_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))
    resolved_in_meeting_id: Mapped[int | None] = db.mapped_column(ForeignKey("meetings.id"))
    resolved_at: Mapped[datetime | None] = db.mapped_column(db.DateTime(timezone=True))


class Decision(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "decisions"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = db.mapped_column(String(300))
    canonical_title: Mapped[str] = db.mapped_column(String(300), default="")
    title_embedding: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    details: Mapped[str] = db.mapped_column(Text, default="")
    created_in_meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"))


class HistoryEvent(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "history_events"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    project_id: Mapped[int] = db.mapped_column(ForeignKey("projects.id"), index=True)
    meeting_id: Mapped[int] = db.mapped_column(ForeignKey("meetings.id"), index=True)
    entity_type: Mapped[str] = db.mapped_column(String(40))
    entity_id: Mapped[int | None] = db.mapped_column(db.Integer)
    event_type: Mapped[str] = db.mapped_column(String(40))
    summary: Mapped[str] = db.mapped_column(Text)
    before_data: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    after_data: Mapped[Any] = db.mapped_column(db.JSON, nullable=True)
    created_at: Mapped[datetime] = db.mapped_column(db.DateTime(timezone=True), default=utcnow)

    review_resolution: Mapped["ReviewResolution"] = db.relationship(
        uselist=False, back_populates="history_event"
    )


class ReviewResolution(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "review_resolutions"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    history_event_id: Mapped[int] = db.mapped_column(
        ForeignKey("history_events.id"), unique=True, index=True
    )
    action: Mapped[str] = db.mapped_column(String(30))
    target_item_id: Mapped[int | None] = db.mapped_column(db.Integer)
    note: Mapped[str] = db.mapped_column(Text, default="")
    created_at: Mapped[datetime] = db.mapped_column(db.DateTime(timezone=True), default=utcnow)

    history_event: Mapped["HistoryEvent"] = db.relationship(back_populates="review_resolution")


class User(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    __tablename__ = "users"

    id: Mapped[int] = db.mapped_column(primary_key=True)
    username: Mapped[str] = db.mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = db.mapped_column(String(255))
    role: Mapped[str] = db.mapped_column(String(20), default="user")


class RevokedToken(db.Model):  # type: ignore[name-defined]  # db.Model is the declarative Base behind the _DB shim
    """
    A logged-out token id, and the moment it stops mattering.

    Logout used to record the id in a set in the process, which meant a
    revoked token became valid again after a restart until its own
    expiry. Persisting it makes revocation survive a restart, and the
    expiry column lets the check discard rows whose token has lapsed
    anyway instead of accumulating forever.

    The id is the primary key so a check is a single index lookup. There
    is deliberately no foreign key to users: a revoked token has to
    outlive the account it belonged to, or deleting a user revives every
    token that user was ever issued.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = db.mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = db.mapped_column(db.DateTime(timezone=True))
