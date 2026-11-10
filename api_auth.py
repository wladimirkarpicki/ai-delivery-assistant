"""
Authentication: JWT HS256 bearer sessions, and the cookie that carries them.

This was a set of closures inside `create_app`, which is the one thing
that made a router split impossible: a closure closes over the state of
the `create_app` call that made it, so a separate module could not import
`get_current_user` to use as a dependency, and a module-level rewrite
that held the state in a global would be worse than it looks.

The reason a global would be worse is specific. `secret_key` is generated
per `create_app` call, and the test suite builds roughly ten apps in one
process. A module-level `secret_key` would make all ten share one signing
key and one revocation set, so every test would keep passing while the
isolation they were written to check quietly disappeared. State therefore
lives on `app.state` and is read per request, which keeps each app
separate and is the same mechanism `request.state.request_id` already
used before this split.

Every function here takes the request (or the app) as an argument rather
than reading anything at import time.
"""

import os
import secrets
import time
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from database import db
from models import RevokedToken, User

_bearer = HTTPBearer(auto_error=False)


def _is_production() -> bool:
    """
    True when the process runs in production mode, where a missing or
    predictable JWT_SECRET_KEY must stop startup instead of silently
    degrading security.
    """
    return (os.environ.get("AIDA_ENV") or "").strip().lower() == "production"


class UserFacingError(ValueError):
    """
    An error whose message was written for the person who triggered it.

    The distinction matters because handlers cannot return arbitrary
    exception text: a provider failure carries the endpoint and status,
    and a database failure carries the statement, and neither belongs in
    a response. Validation failures have to reach the user though, or the
    UI can only say "something went wrong" when the user simply forgot to
    attach a file.

    So validation raises this subclass, and only this subclass is echoed.
    Everything else is logged and replaced with a fixed message. Because
    this is a ValueError, any handler already catching ValueError keeps
    working, which is what let the class be introduced without touching
    the exception tuples.

    It lives here rather than in api.py because more than one router needs
    it, and a router importing api.py would be a cycle: api.py imports the
    routers.
    """


# ---------------------------------------------------------------------------
# Login rate limiting (process-wide, deliberately not per app)

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

# In-process login rate limiting: username -> (failures, first failure ts).
#
# Module-level on purpose, and this is the one piece of state in the file
# that is not per-app: a lockout counter shared between two apps in one
# process costs a test nothing, while a signing key shared between them
# would silently destroy the isolation the tests exist to check. The auth
# router imports these helpers from here rather than through api.py.
_failed_logins: dict = {}


def _register_failed_login(username: str) -> None:
    now = time.monotonic()
    count, first_ts = _failed_logins.get(username, (0, now))

    if now - first_ts > LOGIN_LOCKOUT_SECONDS:
        count, first_ts = 0, now

    _failed_logins[username] = (count + 1, first_ts)


def _login_is_locked(username: str) -> bool:
    entry = _failed_logins.get(username)

    if entry is None:
        return False

    count, first_ts = entry

    if time.monotonic() - first_ts > LOGIN_LOCKOUT_SECONDS:
        _failed_logins.pop(username, None)
        return False

    return count >= LOGIN_MAX_ATTEMPTS


def _clear_failed_logins(username: str) -> None:
    _failed_logins.pop(username, None)


COOKIE_NAME = "aida_token"
COOKIE_PATH = "/"
COOKIE_SAMESITE = "strict"

# Per-app caches of revoked token ids, keyed by app id. A stateless JWT
# cannot be un-issued, so without this the same token stays valid in any
# other browser or device until it expires. Only ids are compared, so
# these hold ids rather than whole sessions.
#
# The set is a cache, not the record. The record is the revoked_tokens
# table: an in-memory set alone meant a logout stopped taking effect after
# a restart, and the token lived for up to TOKEN_TTL_HOURS after that.
# Writing on logout and reading through to the table on a miss is what
# makes revocation survive a restart, and the set still saves a query on
# the hot path for a process that has already revoked the token.
_revoked_ids_by_app: dict[int, set[str]] = {}


# ---------------------------------------------------------------------------
# Request bodies


class CredentialsIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)


class SetupIn(CredentialsIn):
    # The one-time token that gates bootstrap. POST /api/auth/setup has
    # no authenticated caller to check, so this is what keeps an
    # unauthenticated request from creating the admin account.
    #
    # Defaults to empty rather than being required: a missing token is a
    # refused bootstrap, which is the 403 the handler answers on purpose.
    # As a required field pydantic answers 422 first, and the caller is
    # told their payload is malformed when in fact the token they sent is
    # simply wrong.
    bootstrap_token: str = ""


class UserCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8)
    role: str = "user"


class UserPatchIn(BaseModel):
    role: str | None = None
    password: str | None = Field(default=None, min_length=8)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1)
    password: str = Field(min_length=8)


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=8)


# ---------------------------------------------------------------------------
# Token issuance and revocation


def create_token(app, user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(UTC) + app.state.token_ttl,
        # An id per issued token, so one session can be signed out
        # without invalidating the others the same user holds.
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, app.state.jwt_secret_key, algorithm="HS256")


def _revoked_ids(app) -> set[str]:
    return _revoked_ids_by_app.setdefault(id(app), set())


def _is_revoked(app, token_value: str) -> bool:
    """
    True for a token that has been signed out.

    A stateless JWT cannot be un-issued, so without this a logout only
    clears the cookie in one browser while the same token stays valid
    anywhere else until it expires. Only ids are compared, so memory
    holds ids rather than whole sessions.
    """

    try:
        payload = jwt.decode(
            token_value,
            app.state.jwt_secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
    except (jwt.PyJWTError, TypeError, ValueError):
        return False

    if not jti:
        return False

    if jti in _revoked_ids(app):
        return True

    # A miss in the cache is answered from the table, which is where the
    # answer survives a restart. The id is the primary key, so this is
    # one index lookup, on the same query path the user lookup takes.
    row = db.session.get(RevokedToken, jti)

    if row is None:
        return False

    _revoked_ids(app).add(jti)
    return True


def _expiry_from_payload(payload) -> datetime:
    """
    The token's own expiry, as a UTC datetime.

    Stored with the revocation so a row can be dropped once its token has
    lapsed anyway. A payload with no exp falls back to now, which makes
    the row immediately prunable rather than permanent: the token carries
    no expiry to wait out, so there is nothing to protect by keeping it.
    """

    exp = payload.get("exp") if isinstance(payload, dict) else None

    if not isinstance(exp, (int, float)):
        return datetime.now(UTC)

    return datetime.fromtimestamp(exp, tz=UTC)


def revoke_token(app, token_value: str) -> None:
    """Record a signed-out token in the table, and in this app's cache."""

    try:
        payload = jwt.decode(
            token_value,
            app.state.jwt_secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
    except (jwt.PyJWTError, TypeError, ValueError):
        return

    if not jti:
        return

    if db.session.get(RevokedToken, jti) is None:
        db.session.add(
            RevokedToken(jti=jti, expires_at=_expiry_from_payload(payload))
        )
    db.session.commit()
    _revoked_ids(app).add(jti)


def prune_revoked_rows() -> int:
    """
    Drop revoked-token rows whose token has expired.

    Called on logout rather than on a request path: it is not on the hot
    path, and a table holding rows whose token no longer matters is
    clutter rather than a security issue. Returns the number removed so a
    caller can log it.
    """

    try:
        removed = (
            db.session.query(RevokedToken)
            .filter(RevokedToken.expires_at < datetime.now(UTC))
            .delete(synchronize_session=False)
        )
        db.session.commit()
        return int(removed or 0)
    except Exception:  # noqa: BLE001  # a prune failure is never worth a 500
        db.session.rollback()
        return 0


# ---------------------------------------------------------------------------
# Cookie handling


def _is_https(request: Request) -> bool:
    """
    True when the request arrived over TLS.

    Terminating the proxy in front of the app is common, so honour
    X-Forwarded-Proto in addition to the scheme the ASGI server saw.
    """

    forwarded = request.headers.get("x-forwarded-proto", "")

    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"

    return request.url.scheme == "https"


def set_auth_cookie(app, response, token: str, request: Request) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(app.state.token_ttl.total_seconds()),
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=_is_https(request),
    )


def clear_auth_cookie(response) -> None:
    """Drop the session cookie, for a token that has become invalid."""

    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


# ---------------------------------------------------------------------------
# Request dependencies


def read_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    """The cookie is preferred: it is the form no script can read."""

    if credentials is not None:
        return credentials.credentials

    return request.cookies.get(COOKIE_NAME)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    token_value = read_token(request, credentials)

    if not token_value:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    if _is_revoked(request.app, token_value):
        raise HTTPException(status_code=401, detail="Session has ended.")

    try:
        payload = jwt.decode(
            token_value,
            request.app.state.jwt_secret_key,
            algorithms=["HS256"],
        )
        user_id = int(payload.get("sub", ""))
    except (jwt.PyJWTError, TypeError, ValueError) as exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exception

    user = db.session.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")

    return {"id": user.id, "username": user.username, "role": user.role}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only.")
    return user


# ---------------------------------------------------------------------------
# Installation


def install_auth(app, secret_key: str, token_ttl: timedelta) -> None:
    """
    Put the per-app auth state where the functions above can reach it.

    Called by the application factory with a freshly generated secret, so
    two apps built in one process never share a signing key.
    """

    app.state.jwt_secret_key = secret_key
    app.state.token_ttl = token_ttl
    app.state.cookie_name = COOKIE_NAME
    app.state.cookie_path = COOKIE_PATH
    app.state.cookie_samesite = COOKIE_SAMESITE
    _revoked_ids_by_app[id(app)] = set()
