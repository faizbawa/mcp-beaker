"""Tests for system tools (read and write)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from xmlrpc.client import DateTime

import httpx

from mcp_beaker.exceptions import BeakerError, BeakerNotFoundError
from mcp_beaker.servers.systems import (
    _build_advancedsearch_params,
    _parse_json_systems,
    get_system_arches,
    get_system_details,
    get_system_history,
    get_system_status,
    list_systems,
    loan_system,
    power_system,
    provision_system,
    release_system,
    reserve_system,
    return_loan,
    search_systems,
)

import json

SYSTEMS_JSON = json.dumps({
    "items": [
        {"fqdn": "host1.example.com", "arches": ["x86_64"], "status": "Automated",
         "type": "Machine", "vendor": None, "model": None, "loaned_to": None, "reserved_for": None},
        {"fqdn": "host2.example.com", "arches": ["aarch64"], "status": "Automated",
         "type": "Machine", "vendor": None, "model": None, "loaned_to": None, "reserved_for": None},
    ],
    "pagination": {"page": 1, "page_size": 20, "total_count": 2, "total_pages": 1,
                    "has_next": False, "has_prev": False},
})


# ---- _parse_json_systems helper --------------------------------------------


class TestParseJsonSystems:
    def test_parses_entries(self):
        data = json.loads(SYSTEMS_JSON)
        systems = _parse_json_systems(data)
        assert len(systems) == 2
        assert systems[0].fqdn == "host1.example.com"
        assert systems[1].fqdn == "host2.example.com"

    def test_empty_result(self):
        data = {"items": [], "pagination": {"total_count": 0}}
        systems = _parse_json_systems(data)
        assert systems == []


# ---- list_systems ----------------------------------------------------------


class TestListSystems:
    async def test_success(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SYSTEMS_JSON,
                                       headers={"content-type": "application/json"}))
        result = await list_systems(ctx)
        assert "host1.example.com" in result
        assert "host2.example.com" in result

    async def test_invalid_filter(self, ctx):
        result = await list_systems(ctx, filter_type="bogus")
        assert "Error" in result
        assert "Invalid filter_type" in result

    async def test_preset_free(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SYSTEMS_JSON,
                                       headers={"content-type": "application/json"}))
        result = await list_systems(ctx, filter_type="free")
        assert "host1.example.com" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        assert ("preset", "free") in params

    async def test_preset_all_no_preset_param(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SYSTEMS_JSON,
                                       headers={"content-type": "application/json"}))
        result = await list_systems(ctx, filter_type="all")
        assert "host1.example.com" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        assert all(k != "preset" for k, _ in params)

    async def test_hostname_filter(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SYSTEMS_JSON,
                                       headers={"content-type": "application/json"}))
        result = await list_systems(ctx, filter_type="free", hostname="ampere-mtsnow%")
        assert "host1.example.com" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        assert ("preset", "free") in params
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Name,contains,ampere-mtsnow" in adv

    async def test_hostname_without_wildcard(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SYSTEMS_JSON,
                                       headers={"content-type": "application/json"}))
        await list_systems(ctx, hostname="nvidia-grace-hopper")
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Name,contains,nvidia-grace-hopper" in adv

    async def test_connection_error(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(side_effect=BeakerError("conn err"))
        result = await list_systems(ctx)
        assert "Error" in result


# ---- _build_advancedsearch_params helper -----------------------------------


class TestBuildAdvancedSearchParams:
    def test_single_filter(self):
        params = _build_advancedsearch_params({"cpu_vendor": "GenuineIntel"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "CPU/Vendor,is,GenuineIntel" in adv

    def test_multiple_filters(self):
        params = _build_advancedsearch_params({
            "cpu_vendor": "GenuineIntel",
            "cpu_family": 6,
            "cpu_model": 143,
        })
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "CPU/Vendor,is,GenuineIntel" in adv
        assert "CPU/Family,is,6" in adv
        assert "CPU/Model,is,143" in adv

    def test_comparison_operators(self):
        params = _build_advancedsearch_params({"cpu_cores": ">=64"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "CPU/Cores,greater than,64" in adv

        params = _build_advancedsearch_params({"memory": "<=131072"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Memory,less than,131072" in adv

    def test_unknown_key_ignored(self):
        params = _build_advancedsearch_params({"nonexistent_field": "value"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert len(adv) == 0

    def test_page_size_included(self):
        params = _build_advancedsearch_params({"arch": "aarch64"}, limit=25)
        sizes = [v for k, v in params if k == "page_size"]
        assert "25" in sizes

    def test_hostname_always_contains(self):
        params = _build_advancedsearch_params({"hostname": "ampere-mtsnow"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Name,contains,ampere-mtsnow" in adv

        params = _build_advancedsearch_params({"hostname": "%ampere-one-x%"})
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Name,contains,ampere-one-x" in adv


# ---- search_systems --------------------------------------------------------


SEARCH_JSON = json.dumps({
    "items": [
        {"fqdn": "spr-host1.example.com", "arches": ["x86_64"], "status": "Automated",
         "type": "Machine", "vendor": "Dell", "model": "R660", "loaned_to": None, "reserved_for": None},
        {"fqdn": "spr-host2.example.com", "arches": ["x86_64"], "status": "Automated",
         "type": "Machine", "vendor": "Dell", "model": "R660", "loaned_to": None, "reserved_for": None},
    ],
    "pagination": {"page": 1, "page_size": 10, "total_count": 2, "total_pages": 1,
                    "has_next": False, "has_prev": False},
})


class TestSearchSystems:
    async def test_search_by_cpu(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(
            ctx,
            cpu_vendor="GenuineIntel",
            cpu_family=6,
            cpu_model=143,
        )
        assert "spr-host1.example.com" in result
        assert "spr-host2.example.com" in result
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "CPU/Vendor,is,GenuineIntel" in adv

    async def test_search_with_pool_and_arch(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, arch="aarch64", pool="kernel-arm-pool")
        assert "2 system(s)" in result

    async def test_search_no_results(self, ctx, mock_client):
        empty_json = json.dumps({"items": [], "pagination": {"total_count": 0}})
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=empty_json,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, cpu_vendor="NonExistent")
        assert "No systems found" in result

    async def test_search_no_filters(self, ctx):
        result = await search_systems(ctx, status="")
        assert "Error" in result
        assert "At least one" in result

    async def test_search_error(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(side_effect=BeakerError("timeout"))
        result = await search_systems(ctx, cpu_vendor="GenuineIntel")
        assert "Error" in result

    async def test_search_bad_json(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text="not json",
                                       headers={"content-type": "text/plain"}))
        result = await search_systems(ctx, cpu_vendor="GenuineIntel")
        assert "Error" in result

    async def test_search_memory_range(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, memory=">=131072")
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Memory,greater than,131072" in adv

    async def test_search_by_owner(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, owner="tasharma", status="")
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Owner,is,tasharma" in adv

    async def test_search_by_loaned_to(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, loaned_to="tasharma", status="")
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/LoanedTo,is,tasharma" in adv

    async def test_search_by_user(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, user="smitterl", status="")
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/User,is,smitterl" in adv

    async def test_search_by_hostname(self, ctx, mock_client):
        mock_client.rest_get = AsyncMock(
            return_value=httpx.Response(200, text=SEARCH_JSON,
                                       headers={"content-type": "application/json"}))
        result = await search_systems(ctx, hostname="spr-host", status="")
        assert "2 system(s)" in result
        call_kwargs = mock_client.rest_get.call_args
        params = call_kwargs.kwargs.get("params", [])
        adv = [v for k, v in params if k == "advancedsearch"]
        assert "System/Name,contains,spr-host" in adv


# ---- get_system_details ----------------------------------------------------


class TestGetSystemDetails:
    async def test_success(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(
            return_value={
                "fqdn": "host1.example.com",
                "status": "Automated",
                "type": "Machine",
                "arches": ["x86_64"],
                "owner": {"user_name": "admin"},
                "lab_controller": {"fqdn": "lc1"},
                "lender": None,
                "location": None,
                "serial_number": None,
                "model": None,
                "vendor": None,
                "mac_address": None,
                "memory": 16384,
                "numa_nodes": 2,
                "cpu_vendor": "GenuineIntel",
                "cpu_model_name": "Intel(R) Xeon(R) Gold 6454S",
                "cpu_family": 6,
                "cpu_model": 143,
                "cpu_stepping": 8,
                "cpu_speed": 3400.0,
                "cpu_processors": 128,
                "cpu_cores": 64,
                "cpu_sockets": 2,
                "cpu_hyper": True,
                "cpu_flags": ["lm", "fpu", "sse", "sse2", "avx", "avx2"],
                "pools": ["rhelvirt-gating", "virt"],
            }
        )
        result = await get_system_details(ctx, fqdn="host1.example.com")
        assert "host1.example.com" in result
        assert "x86_64" in result
        assert "GenuineIntel" in result
        assert "Intel(R) Xeon(R) Gold 6454S" in result
        assert "Sockets: 2" in result
        assert "Cores: 64" in result
        assert "Hyper-Threading: Yes" in result
        assert "rhelvirt-gating" in result
        assert "virt" in result

    async def test_success_with_loan(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(
            return_value={
                "fqdn": "host1.example.com",
                "status": "Manual",
                "type": "Machine",
                "arches": ["x86_64"],
                "owner": {"user_name": "admin"},
                "current_loan": {
                    "recipient": "jdoe",
                    "recipient_user": {"user_name": "jdoe", "email_address": "jdoe@test.com"},
                    "comment": "RHEL-10 testing",
                },
                "current_reservation": {
                    "user": {"user_name": "jdoe"},
                    "recipe_id": 54321,
                },
            }
        )
        result = await get_system_details(ctx, fqdn="host1.example.com")
        assert "Loaned To: jdoe" in result
        assert "Loan Comment: RHEL-10 testing" in result
        assert "Reserved By: jdoe" in result
        assert "R:54321" in result

    async def test_not_found(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(side_effect=BeakerNotFoundError("not found"))
        result = await get_system_details(ctx, fqdn="ghost.example.com")
        assert "not found" in result.lower()

    async def test_generic_error(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(side_effect=RuntimeError("boom"))
        result = await get_system_details(ctx, fqdn="host")
        assert "Error" in result


# ---- get_system_status -----------------------------------------------------


class TestGetSystemStatus:
    async def test_no_loan(self, ctx, mock_client):
        result = await get_system_status(ctx, fqdn="host1.example.com")
        assert "Automated" in result
        assert "(not loaned)" in result
        assert "(not reserved)" in result

    async def test_with_loan(self, ctx, mock_client):
        mock_client.systems_status = AsyncMock(return_value={
            "condition": "Manual",
            "current_loan": {
                "recipient": "jdoe",
                "recipient_user": {"user_name": "jdoe", "email_address": "jdoe@test.com"},
                "comment": "Kernel testing",
            },
            "current_reservation": None,
        })
        result = await get_system_status(ctx, fqdn="host1.example.com")
        assert "jdoe" in result
        assert "Kernel testing" in result
        assert "Manual" in result

    async def test_with_reservation(self, ctx, mock_client):
        mock_client.systems_status = AsyncMock(return_value={
            "condition": "Automated",
            "current_loan": None,
            "current_reservation": {
                "user": {"user_name": "jdoe"},
                "recipe_id": 12345,
            },
        })
        result = await get_system_status(ctx, fqdn="host1.example.com")
        assert "jdoe" in result
        assert "R:12345" in result

    async def test_not_found(self, ctx, mock_client):
        mock_client.systems_status = AsyncMock(side_effect=BeakerNotFoundError("not found"))
        result = await get_system_status(ctx, fqdn="ghost.example.com")
        assert "not found" in result.lower()

    async def test_generic_error(self, ctx, mock_client):
        mock_client.systems_status = AsyncMock(side_effect=RuntimeError("boom"))
        result = await get_system_status(ctx, fqdn="host1")
        assert "Error" in result


# ---- get_system_history ----------------------------------------------------


class TestGetSystemHistory:
    async def test_success(self, ctx, mock_client):
        result = await get_system_history(ctx, fqdn="host1.example.com")
        assert "testuser" in result

    async def test_xmlrpc_datetime(self, ctx, mock_client):
        """DateTime objects from XML-RPC should be stringified automatically."""
        mock_client.systems_history = AsyncMock(
            return_value=[
                {
                    "created": DateTime("20260312T10:00:00"),
                    "user": "testuser",
                    "service": "XMLRPC",
                    "action": "Changed",
                    "field_name": "User",
                    "old_value": "admin",
                    "new_value": "testuser",
                },
            ]
        )
        result = await get_system_history(ctx, fqdn="host1.example.com")
        assert "testuser" in result

    async def test_with_since(self, ctx, mock_client):
        await get_system_history(ctx, fqdn="host1", since="2026-01-01T00:00:00")
        mock_client.systems_history.assert_awaited_with("host1", "2026-01-01T00:00:00")

    async def test_without_since(self, ctx, mock_client):
        await get_system_history(ctx, fqdn="host1")
        mock_client.systems_history.assert_awaited_with("host1", None)

    async def test_error(self, ctx, mock_client):
        mock_client.systems_history = AsyncMock(side_effect=BeakerError("fail"))
        result = await get_system_history(ctx, fqdn="h")
        assert "Error" in result


# ---- get_system_arches -----------------------------------------------------


class TestGetSystemArches:
    async def test_success(self, ctx, mock_client):
        result = await get_system_arches(ctx, fqdn="host1")
        assert "x86_64" in result
        assert "aarch64" in result

    async def test_error(self, ctx, mock_client):
        mock_client.systems_get_osmajor_arches = AsyncMock(side_effect=BeakerError("deny"))
        result = await get_system_arches(ctx, fqdn="host1")
        assert "Error" in result


# ---- reserve_system --------------------------------------------------------


class TestReserveSystem:
    async def test_success(self, ctx, mock_client):
        result = await reserve_system(ctx, fqdn="host1.example.com")
        assert "reserved" in result.lower()
        mock_client.systems_reserve.assert_awaited_with("host1.example.com")

    async def test_error(self, ctx, mock_client):
        mock_client.systems_reserve = AsyncMock(side_effect=BeakerError("already in use"))
        result = await reserve_system(ctx, fqdn="host1")
        assert "Error" in result
        assert "already in use" in result


# ---- release_system --------------------------------------------------------


class TestReleaseSystem:
    async def test_success(self, ctx, mock_client):
        result = await release_system(ctx, fqdn="host1.example.com")
        assert "released" in result.lower()

    async def test_error(self, ctx, mock_client):
        mock_client.systems_release = AsyncMock(side_effect=BeakerError("not yours"))
        result = await release_system(ctx, fqdn="host1")
        assert "Error" in result


# ---- power_system ----------------------------------------------------------


class TestPowerSystem:
    async def test_reboot(self, ctx, mock_client):
        result = await power_system(ctx, fqdn="host1", action="reboot")
        assert "reboot" in result.lower()
        mock_client.systems_power.assert_awaited_with("reboot", "host1", force=False)

    async def test_on(self, ctx, mock_client):
        result = await power_system(ctx, fqdn="host1", action="on")
        assert "on" in result.lower()

    async def test_off_with_force(self, ctx, mock_client):
        result = await power_system(ctx, fqdn="host1", action="off", force=True)
        assert "off" in result.lower()
        mock_client.systems_power.assert_awaited_with("off", "host1", force=True)

    async def test_invalid_action(self, ctx):
        result = await power_system(ctx, fqdn="host1", action="destroy")
        assert "Error" in result
        assert "Invalid action" in result

    async def test_error(self, ctx, mock_client):
        mock_client.systems_power = AsyncMock(side_effect=BeakerError("denied"))
        result = await power_system(ctx, fqdn="host1", action="reboot")
        assert "Error" in result


# ---- provision_system ------------------------------------------------------


class TestProvisionSystem:
    async def test_success(self, ctx, mock_client):
        result = await provision_system(ctx, fqdn="host1", distro_tree_id=100)
        assert "Provisioning" in result
        mock_client.systems_provision.assert_awaited_once()
        call_kwargs = mock_client.systems_provision.call_args
        assert call_kwargs[0][0] == "host1"
        assert call_kwargs[0][1] == 100

    async def test_with_options(self, ctx, mock_client):
        result = await provision_system(
            ctx,
            fqdn="host1",
            distro_tree_id=100,
            ks_meta="autopart",
            kernel_options="ks=nfs",
            reboot=False,
        )
        assert "Provisioning" in result
        mock_client.systems_provision.assert_awaited_once()

    async def test_error(self, ctx, mock_client):
        mock_client.systems_provision = AsyncMock(side_effect=BeakerError("no perms"))
        result = await provision_system(ctx, fqdn="host1", distro_tree_id=100)
        assert "Error" in result


# ---- loan_system -----------------------------------------------------------


class TestLoanSystem:
    async def test_loan_to_recipient(self, ctx, mock_client):
        result = await loan_system(ctx, fqdn="host1.example.com", recipient="jdoe")
        assert "loaned" in result.lower()
        assert "jdoe" in result
        mock_client.systems_loan_grant.assert_awaited_with(
            "host1.example.com",
            recipient="jdoe",
            comment="",
        )

    async def test_loan_to_self(self, ctx, mock_client):
        result = await loan_system(ctx, fqdn="host1.example.com")
        assert "loaned" in result.lower()
        assert "yourself" in result
        mock_client.systems_loan_grant.assert_awaited_with(
            "host1.example.com",
            recipient=None,
            comment="",
        )

    async def test_loan_with_comment(self, ctx, mock_client):
        result = await loan_system(
            ctx,
            fqdn="host1",
            recipient="jdoe",
            comment="TPM testing",
        )
        assert "loaned" in result.lower()
        mock_client.systems_loan_grant.assert_awaited_with(
            "host1",
            recipient="jdoe",
            comment="TPM testing",
        )

    async def test_error(self, ctx, mock_client):
        mock_client.systems_loan_grant = AsyncMock(
            side_effect=BeakerError("no permission"),
        )
        result = await loan_system(ctx, fqdn="host1", recipient="jdoe")
        assert "Error" in result
        assert "no permission" in result

    async def test_generic_error(self, ctx, mock_client):
        mock_client.systems_loan_grant = AsyncMock(side_effect=RuntimeError("boom"))
        result = await loan_system(ctx, fqdn="host1")
        assert "Error" in result


# ---- return_loan -----------------------------------------------------------


class TestReturnLoan:
    async def test_success(self, ctx, mock_client):
        result = await return_loan(ctx, fqdn="host1.example.com")
        assert "returned" in result.lower()
        mock_client.systems_loan_return.assert_awaited_with("host1.example.com")

    async def test_error(self, ctx, mock_client):
        mock_client.systems_loan_return = AsyncMock(
            side_effect=BeakerError("no active loan"),
        )
        result = await return_loan(ctx, fqdn="host1")
        assert "Error" in result
        assert "no active loan" in result

    async def test_generic_error(self, ctx, mock_client):
        mock_client.systems_loan_return = AsyncMock(side_effect=RuntimeError("boom"))
        result = await return_loan(ctx, fqdn="host1")
        assert "Error" in result
