"""Deterministic clock for Bitcoin Lightning mechanism tests."""

import time

import pytest

from .helpers import DEFAULT_CREATED_AT


@pytest.fixture(autouse=True)
def fixed_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep signed invoice timestamps deterministic and initially valid."""
    monkeypatch.setattr(time, "time", lambda: DEFAULT_CREATED_AT)
