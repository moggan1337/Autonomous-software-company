"""Test setup: force simulation mode and an isolated database.

These env vars are set before any `company.*` module is imported, so the cached
settings pick them up. Tests never need a real API key and never touch the
developer's company.db.
"""
import os
import pathlib
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="asc-tests-")
os.environ["COMPANY_SIMULATE"] = "1"
os.environ["COMPANY_DB"] = str(pathlib.Path(_TMP) / "shared.db")

from company.config import Settings  # noqa: E402  (after env is set)
from company.orchestrator import Company  # noqa: E402


@pytest.fixture
def company(tmp_path) -> Company:
    settings = Settings(
        api_key=None,
        model="claude-opus-4-8",
        effort="high",
        db_path=str(tmp_path / "company.db"),
        force_simulate=True,
        budget=25.0,
    )
    c = Company(settings=settings)
    yield c
    c.db.close()
