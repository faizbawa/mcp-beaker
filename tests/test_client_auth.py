"""Tests for BeakerClient authentication strategies (SPNEGO, bkr CLI, password)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mcp_beaker.client import BeakerClient
from mcp_beaker.config import BeakerConfig
from mcp_beaker.exceptions import BeakerAuthenticationError


def _make_client(**overrides) -> BeakerClient:
    defaults = {
        "url": "https://beaker.test.example.com",
        "auth_method": "kerberos",
        "kerberos_backend": "http",
        "ssl_verify": False,
    }
    defaults.update(overrides)
    return BeakerClient(BeakerConfig(**defaults))


# ---------------------------------------------------------------------------
# _use_bkr routing
# ---------------------------------------------------------------------------


class TestUseBkrRouting:
    def test_password_auth_never_uses_bkr(self):
        client = _make_client(auth_method="password", username="u", password="p")
        assert client._use_bkr is False

    @patch("mcp_beaker.client._HAS_GSSAPI", True)
    def test_http_backend_does_not_use_bkr(self):
        client = _make_client(kerberos_backend="http")
        assert client._use_bkr is False

    @patch("mcp_beaker.client._HAS_GSSAPI", False)
    def test_http_backend_raises_when_gssapi_missing(self):
        client = _make_client(kerberos_backend="http")
        with pytest.raises(BeakerAuthenticationError, match="gssapi"):
            _ = client._use_bkr

    @patch("mcp_beaker.client.bkr_cli.is_bkr_available", return_value=True)
    def test_bkr_backend_uses_bkr(self, _mock_avail):
        client = _make_client(kerberos_backend="bkr")
        assert client._use_bkr is True

    @patch("mcp_beaker.client.bkr_cli.is_bkr_available", return_value=False)
    def test_bkr_backend_raises_when_bkr_missing(self, _mock_avail):
        client = _make_client(kerberos_backend="bkr")
        with pytest.raises(BeakerAuthenticationError, match="bkr"):
            _ = client._use_bkr


# ---------------------------------------------------------------------------
# _ensure_spnego_auth
# ---------------------------------------------------------------------------


class TestSpnegoAuth:
    @patch("mcp_beaker.client._HAS_GSSAPI", False)
    def test_raises_when_gssapi_missing(self):
        client = _make_client()
        with pytest.raises(BeakerAuthenticationError, match="gssapi"):
            client._ensure_spnego_auth()

    @patch("mcp_beaker.client._HAS_GSSAPI", True)
    def test_skips_when_already_authenticated(self):
        client = _make_client()
        client._authenticated = True
        client._ensure_spnego_auth()

    @patch("mcp_beaker.client._HAS_GSSAPI", True)
    @patch("mcp_beaker.client.gssapi")
    @patch("mcp_beaker.client.httpx.get")
    def test_successful_spnego(self, mock_httpx_get, mock_gssapi):
        mock_ctx = MagicMock()
        mock_ctx.step.return_value = b"fake-token"
        mock_gssapi.SecurityContext.return_value = mock_ctx
        mock_gssapi.Name.return_value = MagicMock()
        mock_gssapi.NameType.hostbased_service = "hostbased"

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.cookies = httpx.Cookies()
        mock_response.cookies.set("beaker_auth_token", "test-session-token")
        mock_response.status_code = 200
        mock_httpx_get.return_value = mock_response

        client = _make_client()
        client._ensure_spnego_auth()

        assert client._authenticated is True
        assert client._session_cookie == "test-session-token"
        assert any(
            "beaker_auth_token=test-session-token" in c
            for c in client._cookie_transport._cookies
        )

    @patch("mcp_beaker.client._HAS_GSSAPI", True)
    @patch("mcp_beaker.client.gssapi")
    @patch("mcp_beaker.client.httpx.get")
    def test_raises_when_no_cookie(self, mock_httpx_get, mock_gssapi):
        mock_ctx = MagicMock()
        mock_ctx.step.return_value = b"fake-token"
        mock_gssapi.SecurityContext.return_value = mock_ctx
        mock_gssapi.Name.return_value = MagicMock()
        mock_gssapi.NameType.hostbased_service = "hostbased"

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.cookies = httpx.Cookies()
        mock_response.status_code = 200
        mock_response.text = "no cookie here"
        mock_httpx_get.return_value = mock_response

        client = _make_client()
        with pytest.raises(BeakerAuthenticationError, match="session cookie"):
            client._ensure_spnego_auth()


# ---------------------------------------------------------------------------
# Session cookie injection into REST calls
# ---------------------------------------------------------------------------


class TestSessionCookieInjection:
    async def test_rest_get_includes_cookie(self):
        client = _make_client()
        client._session_cookie = "my-cookie"

        captured_cookies = {}

        async def _fake_get(url, *, headers=None, params=None, timeout=None):
            resp = MagicMock(spec=httpx.Response)
            resp.url = url
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                captured_cookies.update(kwargs.get("cookies", {}))

            async def __aenter__(self):
                self.get = _fake_get
                return self

            async def __aexit__(self, *args):
                pass

        with patch("mcp_beaker.client.httpx.AsyncClient", FakeAsyncClient):
            await client.rest_get("/test")

        assert captured_cookies.get("beaker_auth_token") == "my-cookie"

    async def test_rest_get_no_cookie_when_not_set(self):
        client = _make_client(auth_method="password", username="u", password="p")

        captured_cookies = {}

        async def _fake_get(url, *, headers=None, params=None, timeout=None):
            resp = MagicMock(spec=httpx.Response)
            resp.url = url
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

        class FakeAsyncClient:
            def __init__(self, **kwargs):
                captured_cookies.update(kwargs.get("cookies", {}))

            async def __aenter__(self):
                self.get = _fake_get
                return self

            async def __aexit__(self, *args):
                pass

        with patch("mcp_beaker.client.httpx.AsyncClient", FakeAsyncClient):
            await client.rest_get("/test")

        assert "beaker_auth_token" not in captured_cookies


# ---------------------------------------------------------------------------
# _reauth dispatches correctly
# ---------------------------------------------------------------------------


class TestReauth:
    def test_reauth_password(self):
        client = _make_client(auth_method="password", username="u", password="p")
        with patch.object(client, "_ensure_password_auth") as mock_pw:
            client._reauth()
            mock_pw.assert_called_once()

    def test_reauth_kerberos_http(self):
        client = _make_client(kerberos_backend="http")
        with patch.object(client, "_ensure_spnego_auth") as mock_spnego:
            client._reauth()
            mock_spnego.assert_called_once()

    def test_reauth_kerberos_bkr_is_noop(self):
        """When bkr backend is selected, _reauth does nothing (bkr handles auth)."""
        client = _make_client(kerberos_backend="bkr")
        client._reauth()


# ---------------------------------------------------------------------------
# call_xmlrpc_authenticated routing
# ---------------------------------------------------------------------------


class TestCallXmlrpcAuthenticated:
    async def test_routes_kerberos_http_to_spnego(self):
        client = _make_client(kerberos_backend="http")
        with (
            patch.object(client, "_ensure_spnego_auth") as mock_spnego,
            patch.object(client, "call_xmlrpc", return_value="ok") as mock_rpc,
        ):
            result = await client.call_xmlrpc_authenticated("auth.who_am_i")
            mock_spnego.assert_called_once()
            mock_rpc.assert_awaited_once_with("auth.who_am_i")
            assert result == "ok"

    async def test_kerberos_bkr_skips_spnego(self):
        client = _make_client(kerberos_backend="bkr")
        with (
            patch.object(client, "_ensure_spnego_auth") as mock_spnego,
            patch.object(client, "call_xmlrpc", return_value="ok") as mock_rpc,
        ):
            result = await client.call_xmlrpc_authenticated("auth.who_am_i")
            mock_spnego.assert_not_called()
            mock_rpc.assert_awaited_once_with("auth.who_am_i")
            assert result == "ok"

    async def test_routes_password_to_password_auth(self):
        client = _make_client(auth_method="password", username="u", password="p")
        with (
            patch.object(client, "_ensure_password_auth") as mock_pw,
            patch.object(client, "call_xmlrpc", return_value="ok") as mock_rpc,
        ):
            result = await client.call_xmlrpc_authenticated("auth.who_am_i")
            mock_pw.assert_called_once()
            mock_rpc.assert_awaited_once_with("auth.who_am_i")
            assert result == "ok"
