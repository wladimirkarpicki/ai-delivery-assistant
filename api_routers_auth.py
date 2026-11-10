"""
Authentication and account administration.

These routes stayed inside create_app longer than the others because they
were the reason a router split was impossible: get_current_user,
require_admin, create_token and the cookie helpers were all closures over
the app's own secret key. With those in api_auth as module-level functions
reading app.state, this module is an ordinary router.

The rate-limiting state stays in api.py rather than moving here, because
it is process-wide rather than per-app and the tests build several apps
that are meant to share a lockout counter as little as they are meant to
share a signing key. `_failed_logins` is therefore still reached through
api.py, which is the one import that runs from a router back to the
factory.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from api_auth import (
    CredentialsIn,
    PasswordChangeIn,
    PasswordResetIn,
    SetupIn,
    UserCreateIn,
    UserPatchIn,
    _clear_failed_logins,
    _login_is_locked,
    _register_failed_login,
    clear_auth_cookie,
    create_token,
    get_current_user,
    prune_revoked_rows,
    read_token,
    require_admin,
    revoke_token,
    set_auth_cookie,
)
from config_loader import get_bootstrap_token
from database import db
from models import User

router = APIRouter()


@router.post("/api/auth/setup")
def auth_setup(data: SetupIn, request: Request):
    """
    Create the initial admin. Only available while no user exists,
    and only to a caller who knows the one-time bootstrap token.
    """

    # compare_digest needs bytes; a non-ASCII payload must not raise.
    if not secrets.compare_digest(
        data.bootstrap_token.encode("utf-8"),
        get_bootstrap_token().encode("utf-8"),
    ):
        raise HTTPException(
            status_code=403, detail="Bootstrap token is missing or incorrect."
        )

    if User.query.count() > 0:
        raise HTTPException(status_code=400, detail="Setup is already completed.")

    if len(data.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters."
        )

    if User.query.filter_by(username=data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")

    user = User(
        username=data.username,
        password_hash=generate_password_hash(data.password),
        role="admin",
    )
    db.session.add(user)
    db.session.commit()

    token = create_token(app=request.app, user_id=user.id, username=user.username)
    payload = {
        "access_token": token,
        "token_type": "bearer",  # nosec B105  # token_type is the OAuth2 scheme, not a password
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }

    # The cookie is the form no script can read; the body field stays
    # so older clients keep working until they are migrated off it.
    response = JSONResponse(payload)
    set_auth_cookie(app=request.app, response=response, token=token, request=request)
    return response

@router.post("/api/auth/login")
def auth_login(data: CredentialsIn, request: Request):
    """
    Sign in with rate limiting: five failures per username lock it
    for 15 minutes; a success clears the counter.
    """

    if _login_is_locked(data.username):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again in 15 minutes.",
        )

    user = User.query.filter_by(username=data.username).first()

    if user is None or not check_password_hash(user.password_hash, data.password):
        _register_failed_login(data.username)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    _clear_failed_logins(data.username)

    token = create_token(app=request.app, user_id=user.id, username=user.username)
    payload = {
        "access_token": token,
        "token_type": "bearer",  # nosec B105  # token_type is the OAuth2 scheme, not a password
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }

    response = JSONResponse(payload)
    set_auth_cookie(app=request.app, response=response, token=token, request=request)
    return response

@router.post("/api/auth/logout")
def auth_logout(request: Request):
    """
    End the session by expiring the cookie and revoking the token.

    Clearing the cookie alone is not enough: a JWT is valid wherever
    it is presented, so the same token copied out of a request would
    keep working. The token's id is recorded as signed out so every
    presentation of it is refused, not just this browser's.
    """
    token_value = read_token(request, None)

    if token_value:
        try:
            # Written to the table as well as the cache, so the
            # revocation survives a restart. The row carries the
            # token's own expiry: until then it is the record, and
            # after it is dead weight, which prune_revoked_rows clears.
            revoke_token(app=request.app, token_value=token_value)
        except SQLAlchemyError:
            # The cookie is still cleared and the cache still holds
            # the id, so this browser and this process lose access
            # either way. A failed write means only that the
            # revocation would not survive a restart, and the caller
            # is signed out regardless.
            db.session.rollback()
            logging.getLogger("ai-delivery-assistant.auth").warning(
                "could not persist a token revocation; it applies to this process only",
                exc_info=True,
            )

    response = JSONResponse({"signed_out": True})
    clear_auth_cookie(response)

    # Drop rows whose token already lapsed. Not on a request path, so
    # a logout absorbs the cost of keeping the table bounded.
    pruned = prune_revoked_rows()
    if pruned:
        logging.getLogger("ai-delivery-assistant.auth").debug(
            "pruned %d expired revoked-token row(s)", pruned
        )

    return response

@router.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)) -> dict:
    return user

@router.post("/api/auth/password")
def auth_change_password(
    data: PasswordChangeIn,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Self-service password change; requires the current password.
    """

    account = db.session.get(User, user["id"])

    if account is None:
        raise HTTPException(status_code=401, detail="Account no longer exists.")

    if not check_password_hash(account.password_hash, data.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    account.password_hash = generate_password_hash(data.password)
    db.session.commit()

    return {"ok": True}

# ------------------------------------------------------------------
# Users (admin only)

@router.get("/api/users")
def users_list(admin: dict = Depends(require_admin)) -> list:
    return [
        {
            "id": account.id,
            "username": account.username,
            "role": account.role,
            "is_you": account.id == admin["id"],
        }
        for account in User.query.order_by(User.id).all()
    ]

@router.post("/api/users")
def users_create(data: UserCreateIn, admin: dict = Depends(require_admin)) -> dict:
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be user or admin.")

    if User.query.filter_by(username=data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken.")

    user = User(
        username=data.username,
        password_hash=generate_password_hash(data.password),
        role=data.role,
    )
    db.session.add(user)
    db.session.commit()

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_you": False,
    }

@router.patch("/api/users/{user_id}")
def users_update(
    user_id: int,
    data: UserPatchIn,
    admin: dict = Depends(require_admin),
) -> dict:
    user = db.session.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    new_role = data.role if data.role is not None else user.role

    if new_role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be user or admin.")

    if (
        user.role == "admin"
        and new_role != "admin"
        and User.query.filter_by(role="admin").count() == 1
    ):
        raise HTTPException(
            status_code=400,
            detail="The last remaining admin cannot be demoted.",
        )

    user.role = new_role

    if data.password is not None:
        user.password_hash = generate_password_hash(data.password)

    db.session.commit()

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_you": user.id == admin["id"],
    }

@router.delete("/api/users/{user_id}")
def users_delete(user_id: int, admin: dict = Depends(require_admin)) -> dict:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")

    user = db.session.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.role == "admin" and User.query.filter_by(role="admin").count() == 1:
        raise HTTPException(
            status_code=400,
            detail="The last remaining admin cannot be deleted.",
        )

    db.session.delete(user)
    db.session.commit()

    return {"ok": True}

@router.post("/api/users/{user_id}/password")
def users_reset_password(
    user_id: int,
    data: PasswordResetIn,
    admin: dict = Depends(require_admin),
) -> dict:
    user = db.session.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    user.password_hash = generate_password_hash(data.password)
    db.session.commit()

    return {"ok": True}

