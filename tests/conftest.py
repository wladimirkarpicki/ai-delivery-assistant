"""Pytest harness setup shared by every test module.

The suite pins environment values with os.environ.setdefault
(JWT_SECRET_KEY, BOOTSTRAP_TOKEN) and relies on setdefault precedence:
a value the harness set first must win. config_loader.load_env() applies
a developer .env with load_dotenv(override=True) so that production
always takes .env truth over ambient variables, and that same override
replaces the pinned values mid-test whenever a developer .env sits at
the repository root or above it (27 failed / 86 passed against a real
developer .env; the same against a synthetic one).

This conftest closes that gap from the harness side: for the duration of
every test the load_dotenv call inside load_env() is neutralised, which
reproduces the no-.env environment exactly and makes the suite immune to
whatever a developer's .env happens to contain. The production call path
(config_loader.load_env() -> load_dotenv(override=True)) is not touched;
tests/test_config_loader.py pins both halves of that contract.
"""
import pytest

import config_loader


@pytest.fixture(autouse=True)
def developer_dotenv_stays_out_of_the_test_process(monkeypatch):
    """Immunity: a developer .env must never reach the test process.

    load_dotenv with a no-op here applies no .env at all, which is the
    clean-clone environment the suite was written against. The pinning
    done with os.environ.setdefault at test-module import time therefore
    stays authoritative for the whole test.
    """
    monkeypatch.setattr(config_loader, "load_dotenv", lambda *args, **kwargs: False)