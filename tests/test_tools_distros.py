"""Tests for distro tools: list_distro_trees, list_os_families."""

from __future__ import annotations

from unittest.mock import AsyncMock

from mcp_beaker.exceptions import BeakerConnectionError
from mcp_beaker.servers.distros import list_distro_trees, list_os_families


class TestListDistroTrees:
    async def test_success(self, ctx, mock_client):
        result = await list_distro_trees(ctx, name="RHEL-10%", arch="x86_64")
        assert "RHEL-10.2" in result
        mock_client.distrotrees_filter.assert_awaited_once()
        call_args = mock_client.distrotrees_filter.call_args[0][0]
        assert call_args["name"] == "RHEL-10%"
        assert call_args["arch"] == "x86_64"

    async def test_no_criteria(self, ctx):
        result = await list_distro_trees(ctx)
        assert "Error" in result
        assert "At least one" in result

    async def test_only_limit_not_enough(self, ctx):
        result = await list_distro_trees(ctx, limit=5)
        assert "Error" in result

    async def test_tags_parsed(self, ctx, mock_client):
        await list_distro_trees(ctx, name="RHEL%", tags="STABLE,RELEASED")
        call_args = mock_client.distrotrees_filter.call_args[0][0]
        assert call_args["tags"] == ["STABLE", "RELEASED"]

    async def test_empty_results(self, ctx, mock_client):
        mock_client.distrotrees_filter = AsyncMock(return_value=[])
        result = await list_distro_trees(ctx, family="Fedora99")
        assert "No distro trees" in result

    async def test_error(self, ctx, mock_client):
        mock_client.distrotrees_filter = AsyncMock(
            side_effect=BeakerConnectionError("timeout")
        )
        result = await list_distro_trees(ctx, name="RHEL%")
        assert "Error" in result


class TestListOsFamilies:
    async def test_success(self, ctx, mock_client):
        result = await list_os_families(ctx)
        assert "RedHatEnterpriseLinux10" in result
        assert "Fedora42" in result

    async def test_with_tags(self, ctx, mock_client):
        await list_os_families(ctx, tags="STABLE")
        call_args = mock_client.distros_get_osmajors.call_args[0][0]
        assert call_args == ["STABLE"]

    async def test_no_tags(self, ctx, mock_client):
        await list_os_families(ctx)
        mock_client.distros_get_osmajors.assert_awaited_with(None)

    async def test_empty(self, ctx, mock_client):
        mock_client.distros_get_osmajors = AsyncMock(return_value=[])
        result = await list_os_families(ctx)
        assert "No OS families" in result

    async def test_error(self, ctx, mock_client):
        mock_client.distros_get_osmajors = AsyncMock(side_effect=RuntimeError("fail"))
        result = await list_os_families(ctx)
        assert "Error" in result
