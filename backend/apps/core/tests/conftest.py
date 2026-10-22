"""Pytest configuration and global fixtures for AMAPP core tests."""

from typing import Generator

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_django_cache_per_test() -> Generator[None, None, None]:
    """Ensure clean cache and isolated throttle state between test executions."""
    cache.clear()
    yield
    cache.clear()
