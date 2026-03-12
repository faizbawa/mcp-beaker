"""Tests for general tools: whoami, list_lab_controllers."""

from __future__ import annotations

from unittest.mock import AsyncMock

from mcp_beaker.exceptions import BeakerAuthenticationError
from mcp_beaker.servers.general import list_lab_controllers, whoami


class TestWhoami:
    async def test_success(self, ctx, mock_client):
        result = await whoami(ctx)
        assert "testuser" in result
        assert "test@example.com" in result
        mock_client.whoami.assert_awaited_once()

    async def test_auth_error(self, ctx, mock_client):
        mock_client.whoami = AsyncMock(side_effect=BeakerAuthenticationError("bad creds"))
        result = await whoami(ctx)
        assert "Error" in result
        assert "bad creds" in result

    async def test_unexpected_error(self, ctx, mock_client):
        mock_client.whoami = AsyncMock(side_effect=RuntimeError("boom"))
        result = await whoami(ctx)
        assert "Error" in result
        assert "boom" in result


class TestListLabControllers:
    async def test_success(self, ctx, mock_client):
        result = await list_lab_controllers(ctx)
        assert "lc1.example.com" in result
        assert "lc2.example.com" in result
        mock_client.lab_controllers.assert_awaited_once()

    async def test_empty(self, ctx, mock_client):
        mock_client.lab_controllers = AsyncMock(return_value=[])
        result = await list_lab_controllers(ctx)
        assert "No lab controllers" in result

    async def test_error(self, ctx, mock_client):
        mock_client.lab_controllers = AsyncMock(side_effect=RuntimeError("timeout"))
        result = await list_lab_controllers(ctx)
        assert "Error" in result
