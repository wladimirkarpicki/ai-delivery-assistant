"""
Shared dependencies for the routers.

`_get_project` was a closure inside `create_app` and was called from nine
places across six route groups, which made it the most widely shared
piece of the application after auth. It has no per-app state, so it moved
whole rather than being rewritten to read app.state the way auth was.

`get_router` is the other shared piece, and it does read app.state for a
real reason: the router instance is passed into `create_app`, and the test
suite substitutes a fake one per app. A module-level singleton would make
every app in one process share whatever router was bound last, so the
substituted fake would leak between tests.
"""

from fastapi import Depends, HTTPException

from api_auth import get_current_user, require_admin
from database import db
from models import HistoryEvent, Project


def _get_project(project_id: int) -> Project:
    project = db.session.get(Project, project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return project


def open_review_events(project):
    """
    Review events nobody has resolved yet.

    The `~has()` filter rather than a left join: a resolution row existing
    is what "resolved" means here, and two queries against the ORM read
    more clearly than one outer join that has to be explained.
    """

    return (
        HistoryEvent.query.filter_by(
            project_id=project.id,
            event_type="needs_review",
        )
        .filter(~HistoryEvent.review_resolution.has())
        .order_by(HistoryEvent.id.desc())
        .all()
    )


def get_router(request):
    """The provider router this app was built with."""

    return request.app.state.router


def install_deps(app, router_instance) -> None:
    """Put the per-app router where get_router can reach it."""

    app.state.router = router_instance


# Re-exported so a router module can import its dependencies from one
# place rather than knowing the split between api_auth and api_deps.
__all__ = [
    "Depends",
    "_get_project",
    "get_current_user",
    "get_router",
    "require_admin",
]
