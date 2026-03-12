"""Tests for task tools: search_tasks."""

from __future__ import annotations

from unittest.mock import AsyncMock

from mcp_beaker.exceptions import BeakerXMLRPCError
from mcp_beaker.servers.tasks import search_tasks


class TestSearchTasks:
    async def test_success(self, ctx, mock_client):
        result = await search_tasks(ctx, osmajor="RedHatEnterpriseLinux10")
        assert "/distribution/reservesys" in result
        mock_client.tasks_filter.assert_awaited_once()

    async def test_no_filters(self, ctx):
        result = await search_tasks(ctx)
        assert "Error" in result
        assert "At least one" in result

    async def test_packages_parsed(self, ctx, mock_client):
        await search_tasks(ctx, packages="kernel, glibc")
        call_args = mock_client.tasks_filter.call_args[0][0]
        assert call_args["packages"] == ["kernel", "glibc"]

    async def test_types_parsed(self, ctx, mock_client):
        await search_tasks(ctx, types="Regression,Functional")
        call_args = mock_client.tasks_filter.call_args[0][0]
        assert call_args["types"] == ["Regression", "Functional"]

    async def test_empty_results(self, ctx, mock_client):
        mock_client.tasks_filter = AsyncMock(return_value=[])
        result = await search_tasks(ctx, osmajor="Foo")
        assert "No tasks" in result

    async def test_beaker_error(self, ctx, mock_client):
        mock_client.tasks_filter = AsyncMock(
            side_effect=BeakerXMLRPCError(1, "xmlrpc fault")
        )
        result = await search_tasks(ctx, osmajor="Foo")
        assert "Error" in result

    async def test_unexpected_error(self, ctx, mock_client):
        mock_client.tasks_filter = AsyncMock(side_effect=ValueError("bad value"))
        result = await search_tasks(ctx, distro_name="RHEL")
        assert "Error" in result
