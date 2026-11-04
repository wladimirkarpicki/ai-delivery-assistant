"""Single-point environment loader."""
import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger("ai-delivery-assistant.config")

# Cached one-time bootstrap token; see get_bootstrap_token().
_bootstrap_token: str | None = None


def load_env():
    load_dotenv(override=True)


def get_jwt_secret_key():
    """
    The JWT signing key from the environment (.env: JWT_SECRET_KEY).
    Empty string when not configured; the caller decides the fallback.
    """
    load_env()
    return (os.getenv("JWT_SECRET_KEY") or "").strip()


def get_token_ttl_hours():
    """Bearer token lifetime in hours (the JWT 'exp' claim). Default 12."""
    load_env()

    try:
        return max(1, int(os.getenv("TOKEN_TTL_HOURS") or "12"))
    except ValueError:
        return 12


def _generate_bootstrap_token() -> str:
    token = os.urandom(32).hex()
    logger.warning(
        "BOOTSTRAP_TOKEN is not set; generated an ephemeral one. "
        "POST /api/auth/setup now requires it, and the value changes on "
        "every restart, so it is only usable for a single first run: %s",
        token,
    )
    return token


def get_bootstrap_token() -> str:
    """
    The one-time token that gates POST /api/auth/setup.

    Bootstrap creates an admin with no authentication at all, so an
    unauthenticated caller must never reach it. Set BOOTSTRAP_TOKEN in
    the environment to fix the value; when it is unset a random token is
    generated once per process and logged, so a first run stays possible
    from the console while nothing predictable is left open.
    """
    global _bootstrap_token

    if _bootstrap_token is not None:
        return _bootstrap_token

    load_env()
    configured = (os.getenv("BOOTSTRAP_TOKEN") or "").strip()
    _bootstrap_token = configured or _generate_bootstrap_token()
    return _bootstrap_token


def reset_bootstrap_token() -> None:
    """Drop the cached bootstrap token; used by the test suite."""
    global _bootstrap_token
    _bootstrap_token = None
