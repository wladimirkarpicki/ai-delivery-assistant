from datetime import datetime, timezone

from database import db


def utcnow():
    return datetime.now(timezone.utc)


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    state = db.relationship("ProjectState", back_populates="project", uselist=False, cascade="all, delete-orphan")
    meetings = db.relationship("Meeting", back_populates="project", order_by="Meeting.created_at.desc()")


class ProjectState(db.Model):
    __tablename__ = "project_states"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, unique=True)
    delivery_status = db.Column(db.String(20), nullable=False, default="unknown")
    progress_summary = db.Column(db.Text, nullable=False, default="")
    completed_items = db.Column(db.JSON, nullable=False, default=list)
    in_progress_items = db.Column(db.JSON, nullable=False, default=list)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    updated_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True)

    project = db.relationship("Project", back_populates="state")


class Meeting(db.Model):
    __tablename__ = "meetings"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(250), nullable=False)
    source_filename = db.Column(db.String(255), nullable=True)
    original_text = db.Column(db.Text, nullable=False)
    analysis_text = db.Column(db.Text, nullable=False)
    analysis_json = db.Column(db.JSON, nullable=False)
    provider = db.Column(db.String(30), nullable=False)
    model = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    project = db.relationship("Project", back_populates="meetings")


class Risk(db.Model):
    __tablename__ = "risks"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    impact = db.Column(db.String(20), nullable=False, default="unknown")
    mitigation = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    updated_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    resolved_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)


class ActionItem(db.Model):
    __tablename__ = "action_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    details = db.Column(db.Text, nullable=False, default="")
    owner = db.Column(db.String(160), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    updated_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    completed_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)


class Blocker(db.Model):
    __tablename__ = "blockers"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    created_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    updated_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)
    resolved_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)


class Decision(db.Model):
    __tablename__ = "decisions"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    details = db.Column(db.Text, nullable=False, default="")
    created_in_meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False)


class HistoryEvent(db.Model):
    __tablename__ = "history_events"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meetings.id"), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    event_type = db.Column(db.String(40), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    before_data = db.Column(db.JSON, nullable=True)
    after_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
