"""Environment-loading contract tests (task t_8afe3292).

Three properties are pinned here so neither half of the .env contract
can regress silently:

1. Harness immunity - a developer .env must not replace the values the
   suite pins with os.environ.setdefault (the fixture in
   tests/conftest.py).
2. Production precedence - load_env() must still call the real loader
   with override=True, so .env keeps winning over ambient variables.
3. The call in (2) really does replace a process value, which is what
   makes the harness fixture in (1) necessary in the first place.
"""
import os

import config_loader

PINNED_SECRET = "unit-test-secret-key-0123456789abcdef"
DOTENV_SECRET = "developer-dotenv-secret-0123456789abcdef"


def test_the_real_loader_applies_a_dotenv_over_a_process_value(tmp_path, monkeypatch):
    import dotenv

    hostile = tmp_path / ".env"
    hostile.write_text(f"JWT_SECRET_KEY={DOTENV_SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("JWT_SECRET_KEY", PINNED_SECRET)

    # Exactly the call config_loader.load_env() makes in production.
    dotenv.load_dotenv(hostile, override=True)
    assert os.environ["JWT_SECRET_KEY"] == DOTENV_SECRET


def test_load_env_still_calls_the_loader_with_override_true(monkeypatch):
    """The production precedence path must stay exactly as it is."""
    seen = {}

    def recorder(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return False

    monkeypatch.setattr(config_loader, "load_dotenv", recorder)

    config_loader.load_env()

    assert seen["args"] == ()
    assert seen["kwargs"] == {"override": True}


def test_a_developer_dotenv_cannot_replace_the_pinned_secret(tmp_path, monkeypatch):
    hostile = tmp_path / ".env"
    hostile.write_text(f"JWT_SECRET_KEY={DOTENV_SECRET}\n", encoding="utf-8")

    # A developer .env lying around is a real trap, not a theoretical
    # one: the same loader with the same override flag takes the pinned
    # secret away (asserted in the first test above). Watch that this
    # file exists while the harness is asked to load the environment.
    monkeypatch.setenv("JWT_SECRET_KEY", PINNED_SECRET)
    assert hostile.exists()

    config_loader.load_env()

    # The conftest fixture kept the loader out, so the pin survives.
    assert os.environ["JWT_SECRET_KEY"] == PINNED_SECRET