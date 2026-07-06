"""Test fixtures for the FINX report tools.

The backend config exposes an eagerly-validated ``settings`` singleton, so the
required FINX env vars must exist *before* ``backend.config.settings`` is first
imported. These defaults make the test suite self-contained (no dependency on a
developer's ``.env``); individual tests override them via ``monkeypatch.setenv``
plus ``get_settings.cache_clear()``.
"""

from __future__ import annotations

import os

os.environ.setdefault("FINX_REPORTS_BASE_URL", "https://finxomne.test")
os.environ.setdefault("FINX_CONTRACT_NOTE_BASE_URL", "https://contractnote.test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import pytest

from backend.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Give every test a freshly-loaded settings singleton."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
