"""Tests for the FINX report tools with a mocked httpx.AsyncClient.

No live network: ``httpx.AsyncClient`` is patched with a fake that records the
outgoing request (url/headers/json) and returns a configured response — or
raises a configured exception — so we can assert on both directions.
"""

from __future__ import annotations

import httpx
import pytest

from backend.config import get_settings
from backend.contracts.reports import ReportResult
from backend.contracts.session import SessionContext
from backend.tools import finx_client

SESSION = SessionContext(client_code="X130627", session_token="jwt.token.value")


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = "", bad_json: bool = False):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self._bad_json = bad_json

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        if self._bad_json:
            raise ValueError("no json to decode")
        return self._json


class _FakeAsyncClient:
    """Async-context-manager stand-in for ``httpx.AsyncClient``.

    Records the last request into ``capture`` and either returns ``response`` or
    raises ``exc`` from ``post``.
    """

    def __init__(self, capture: dict, response=None, exc: Exception | None = None, **kwargs):
        self._capture = capture
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, *, json=None, headers=None):
        self._capture["url"] = url
        self._capture["json"] = json
        self._capture["headers"] = headers
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_client(monkeypatch, capture, *, response=None, exc=None):
    def factory(**kwargs):
        return _FakeAsyncClient(capture, response=response, exc=exc, **kwargs)

    monkeypatch.setattr(finx_client.httpx, "AsyncClient", factory)


# --- 4.1 success path -------------------------------------------------------


@pytest.mark.asyncio
async def test_cml_report_success_returns_raw_json(monkeypatch):
    capture: dict = {}
    payload = {"holdings": [{"symbol": "TCS", "qty": 10}]}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, json_data=payload))

    result = await finx_client.cml_report(SESSION, "X130627")

    assert isinstance(result, ReportResult)
    assert result.ok is True
    assert result.report_type == "cml"
    assert result.data == payload
    assert result.error is None


@pytest.mark.asyncio
async def test_contract_note_success_returns_raw_json(monkeypatch):
    capture: dict = {}
    payload = {"contractNote": {"date": "03-07-2026", "trades": []}}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, json_data=payload))

    result = await finx_client.contract_note(SESSION, "9876543210", "03-07-2026")

    assert result.ok is True
    assert result.report_type == "contract-note"
    assert result.data == payload
    assert result.error is None


# --- 4.2 header/body assertions ---------------------------------------------


@pytest.mark.asyncio
async def test_cml_report_sends_finx_headers_and_alias_body(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, json_data={}))

    await finx_client.cml_report(SESSION, "X130627")

    headers = capture["headers"]
    assert headers["Authorization"] == "jwt.token.value"
    assert headers["authType"] == "jwt"
    assert headers["source"] == "FINX_WEB"
    assert capture["json"] == {
        "reportType": "cml",
        "searchBy": "client-id",
        "searchValue": "X130627",
    }
    assert capture["url"].endswith("/mis/reports/generate")


@pytest.mark.asyncio
async def test_contract_note_sends_finx_headers_and_alias_body(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, json_data={}))

    await finx_client.contract_note(SESSION, "9876543210", "03-07-2026")

    headers = capture["headers"]
    assert headers["Authorization"] == "jwt.token.value"
    assert headers["authType"] == "jwt"
    assert headers["source"] == "FINX_WEB"
    assert capture["json"] == {
        "mobileNo": "9876543210",
        "contractDate": "03-07-2026",
    }
    assert capture["url"].endswith("/mis/v2/contract-note/generate")


# --- 4.3 failure paths ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 500])
async def test_non_2xx_status_becomes_structured_error(monkeypatch, status):
    capture: dict = {}
    _patch_client(
        monkeypatch,
        capture,
        response=_FakeResponse(status, text="upstream said no"),
    )

    result = await finx_client.cml_report(SESSION, "X130627")

    assert result.ok is False
    assert result.report_type == "cml"
    assert result.data is None
    assert result.error
    assert str(status) in result.error


@pytest.mark.asyncio
async def test_timeout_becomes_structured_error(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, capture, exc=httpx.TimeoutException("timed out"))

    result = await finx_client.contract_note(SESSION, "9876543210", "03-07-2026")

    assert result.ok is False
    assert result.report_type == "contract-note"
    assert result.data is None
    assert result.error
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_request_error_becomes_structured_error(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, capture, exc=httpx.ConnectError("dns failure"))

    result = await finx_client.cml_report(SESSION, "X130627")

    assert result.ok is False
    assert result.data is None
    assert result.error
    assert "request error" in result.error.lower()


@pytest.mark.asyncio
async def test_invalid_json_on_2xx_becomes_structured_error(monkeypatch):
    capture: dict = {}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, bad_json=True))

    result = await finx_client.cml_report(SESSION, "X130627")

    assert result.ok is False
    assert result.data is None
    assert result.error and "json" in result.error.lower()


# --- 4.4 config-driven contract-note host -----------------------------------


@pytest.mark.asyncio
async def test_contract_note_uses_its_own_configured_host(monkeypatch):
    monkeypatch.setenv("FINX_REPORTS_BASE_URL", "https://reports-host.example")
    monkeypatch.setenv("FINX_CONTRACT_NOTE_BASE_URL", "https://contract-host.example/")
    get_settings.cache_clear()

    capture: dict = {}
    _patch_client(monkeypatch, capture, response=_FakeResponse(200, json_data={}))

    await finx_client.contract_note(SESSION, "9876543210", "03-07-2026")

    assert (
        capture["url"]
        == "https://contract-host.example/mis/v2/contract-note/generate"
    )
    assert "reports-host.example" not in capture["url"]
