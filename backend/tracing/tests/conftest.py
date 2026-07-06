"""Test env bootstrap for the tracing suite.

``backend.config`` builds a validated ``Settings`` singleton at import time, and
several required fields (e.g. ``FINX_REPORTS_BASE_URL``) are unrelated to
tracing. Supply harmless defaults here — before ``backend.config`` is first
imported — so the tracing tests can construct settings without a fully populated
``.env``. Existing environment / ``.env`` values always win via ``setdefault``.
"""

from __future__ import annotations

import os

os.environ.setdefault("FINX_REPORTS_BASE_URL", "http://finx.test.local")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("OPENAI_API_KEY", "sk-openai-test")
