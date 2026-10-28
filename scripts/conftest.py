"""pytest: every test in scripts/ runs on its own store and a current binary."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

import testenv  # noqa: E402

testenv.pin()


@pytest.fixture(autouse=True)
def _own_store():
    """A test that pops IDEV_DATA on its way out must not hand the next one ~/.idev."""
    testenv.pin()
    yield
