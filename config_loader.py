"""Single-point environment loader."""
import os

from dotenv import load_dotenv


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
