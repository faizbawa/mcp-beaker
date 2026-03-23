"""Tests for job tools (5 read + 5 write)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from mcp_beaker.config import BeakerConfig
from mcp_beaker.exceptions import BeakerError, BeakerNotFoundError
from mcp_beaker.servers.jobs import (
    cancel_job,
    clone_job,
    extend_watchdog,
    get_job_logs,
    get_job_results_xml,
    get_job_status,
    list_jobs,
    set_job_response,
    submit_job,
    watch_job,
)

# ---------------------------------------------------------------------------
# list_jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    async def test_success_with_details(self, ctx, mock_client):
        result = await list_jobs(ctx, owner="testuser")
        assert "testuser" in result
        mock_client.jobs_filter.assert_awaited_once()
        mock_client.rest_get_json.assert_awaited()

    async def test_success_without_details(self, ctx, mock_client):
        result = await list_jobs(ctx, owner="testuser", fetch_details=False)
        assert "J:100" in result
        mock_client.rest_get_json.assert_not_awaited()

    async def test_no_jobs(self, ctx, mock_client):
        mock_client.jobs_filter = AsyncMock(return_value=[])
        result = await list_jobs(ctx, owner="nobody")
        assert "No jobs found" in result

    async def test_no_owner(self, ctx, mock_client):
        no_owner_cfg = BeakerConfig(
            url="https://beaker.test.example.com",
            auth_method="password",
            username="testuser",
            password="testpass",
            owner="",
            ssl_verify=False,
        )
        mock_client.config = no_owner_cfg
        result = await list_jobs(ctx)
        assert "Error" in result
        assert "Could not determine username" in result

    async def test_filter_params(self, ctx, mock_client):
        await list_jobs(
            ctx,
            owner="testuser",
            limit=10,
            finished="true",
            min_id=100,
            max_id=200,
            whiteboard="smoke",
        )
        call_args = mock_client.jobs_filter.call_args[0][0]
        assert call_args["owner"] == "testuser"
        assert call_args["limit"] == 10
        assert call_args["is_finished"] is True
        assert call_args["minid"] == 100
        assert call_args["maxid"] == 200
        assert call_args["whiteboard"] == "smoke"

    async def test_finished_false(self, ctx, mock_client):
        await list_jobs(ctx, owner="testuser", finished="false")
        call_args = mock_client.jobs_filter.call_args[0][0]
        assert call_args["is_finished"] is False

    async def test_fallback_to_job_ids_on_rest_failure(self, ctx, mock_client):
        """If all REST detail fetches fail, should fall back to job ID list."""
        mock_client.rest_get_json = AsyncMock(side_effect=RuntimeError("boom"))
        result = await list_jobs(ctx, owner="testuser")
        assert "J:100" in result

    async def test_jobs_filter_error(self, ctx, mock_client):
        mock_client.jobs_filter = AsyncMock(side_effect=BeakerError("fail"))
        result = await list_jobs(ctx, owner="testuser")
        assert "Error" in result


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    async def test_success(self, ctx, mock_client):
        result = await get_job_status(ctx, job_id="J:100")
        assert "J:100" in result

    async def test_numeric_id(self, ctx, mock_client):
        result = await get_job_status(ctx, job_id="100")
        assert "100" in result

    async def test_invalid_id(self, ctx):
        result = await get_job_status(ctx, job_id="abc")
        assert "Error" in result
        assert "Invalid job ID" in result

    async def test_empty_id(self, ctx):
        result = await get_job_status(ctx, job_id="")
        assert "Error" in result
        assert "required" in result

    async def test_not_found(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(side_effect=BeakerNotFoundError("nope"))
        result = await get_job_status(ctx, job_id="J:999")
        assert "not found" in result.lower()

    async def test_generic_error(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(side_effect=RuntimeError("crash"))
        result = await get_job_status(ctx, job_id="J:100")
        assert "Error" in result


# ---------------------------------------------------------------------------
# get_job_results_xml
# ---------------------------------------------------------------------------


class TestGetJobResultsXml:
    async def test_success(self, ctx, mock_client):
        result = await get_job_results_xml(ctx, task_id="J:100")
        assert "cloned" in result
        mock_client.taskactions_to_xml.assert_awaited_with("J:100", clone=False)

    async def test_clone(self, ctx, mock_client):
        await get_job_results_xml(ctx, task_id="J:100", clone=True)
        mock_client.taskactions_to_xml.assert_awaited_with("J:100", clone=True)

    async def test_with_prefix(self, ctx, mock_client):
        await get_job_results_xml(ctx, task_id="RS:4321")
        mock_client.taskactions_to_xml.assert_awaited_with("RS:4321", clone=False)

    async def test_numeric_defaults_to_t_prefix(self, ctx, mock_client):
        await get_job_results_xml(ctx, task_id="99999")
        mock_client.taskactions_to_xml.assert_awaited_with("T:99999", clone=False)

    async def test_invalid_id(self, ctx):
        result = await get_job_results_xml(ctx, task_id="bogus")
        assert "Error" in result

    async def test_error(self, ctx, mock_client):
        mock_client.taskactions_to_xml = AsyncMock(side_effect=BeakerError("fail"))
        result = await get_job_results_xml(ctx, task_id="J:1")
        assert "Error" in result


# ---------------------------------------------------------------------------
# get_job_logs
# ---------------------------------------------------------------------------


class TestGetJobLogs:
    async def test_success(self, ctx, mock_client):
        result = await get_job_logs(ctx, task_id="J:100")
        assert "console.log" in result
        mock_client.taskactions_files.assert_awaited_with("J:100")

    async def test_empty_logs(self, ctx, mock_client):
        mock_client.taskactions_files = AsyncMock(return_value=[])
        result = await get_job_logs(ctx, task_id="J:100")
        assert "No log files" in result

    async def test_invalid_id(self, ctx):
        result = await get_job_logs(ctx, task_id="xyz")
        assert "Error" in result

    async def test_error(self, ctx, mock_client):
        mock_client.taskactions_files = AsyncMock(side_effect=RuntimeError("boom"))
        result = await get_job_logs(ctx, task_id="J:1")
        assert "Error" in result


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------


class TestSubmitJob:
    async def test_empty_xml(self, ctx):
        result = await submit_job(ctx, job_xml="")
        assert "Error" in result

    async def test_whitespace_xml(self, ctx):
        result = await submit_job(ctx, job_xml="   ")
        assert "Error" in result

    async def test_structural_errors(self, ctx):
        result = await submit_job(ctx, job_xml="<job></job>")
        assert "structural errors" in result.lower() or "Error" in result

    async def test_xmlrpc_submit(self, ctx, mock_client):
        """password auth → _use_bkr=False → XML-RPC path (default fixture config)."""
        from tests.conftest import SAMPLE_JOB_XML
        result = await submit_job(ctx, job_xml=SAMPLE_JOB_XML, force=True)
        assert "submitted" in result.lower() or "J:" in result

    @patch("mcp_beaker.utils.bkr_cli.bkr_job_submit", new_callable=AsyncMock)
    @patch("mcp_beaker.utils.bkr_cli.is_bkr_available", return_value=True)
    async def test_bkr_submit(self, _mock_avail, mock_submit, ctx, mock_client):
        mock_client.config = BeakerConfig(
            url="https://beaker.test.example.com",
            auth_method="kerberos",
            kerberos_backend="bkr",
            ssl_verify=False,
        )
        mock_submit.return_value = "J:300"
        from tests.conftest import SAMPLE_JOB_XML
        result = await submit_job(ctx, job_xml=SAMPLE_JOB_XML, force=True)
        assert "J:300" in result
        mock_submit.assert_awaited_once()

    async def test_missing_fields_no_force(self, ctx, mock_client):
        xml = """\
<job>
  <whiteboard>Minimal</whiteboard>
  <recipeSet>
    <recipe>
      <distroRequires>
        <distro_family op="=" value="RedHatEnterpriseLinux10"/>
        <distro_arch op="=" value="x86_64"/>
      </distroRequires>
      <hostRequires/>
      <task name="/distribution/reservesys" role="STANDALONE"/>
    </recipe>
  </recipeSet>
</job>"""
        result = await submit_job(ctx, job_xml=xml)
        has_autofill = "auto-filled" in result.lower()
        has_missing = "need your input" in result.lower()
        assert has_autofill or has_missing or "Error" in result


# ---------------------------------------------------------------------------
# clone_job
# ---------------------------------------------------------------------------


class TestCloneJob:
    async def test_success(self, ctx, mock_client):
        """password auth → _use_bkr=False → XML-RPC path."""
        result = await clone_job(ctx, job_id="J:100")
        mock_client.taskactions_to_xml.assert_awaited_with("J:100", clone=True)
        assert "submitted" in result.lower() or "J:" in result

    async def test_invalid_id(self, ctx):
        result = await clone_job(ctx, job_id="abc")
        assert "Error" in result

    async def test_xml_fetch_error(self, ctx, mock_client):
        mock_client.taskactions_to_xml = AsyncMock(side_effect=BeakerError("gone"))
        result = await clone_job(ctx, job_id="J:100")
        assert "Error" in result


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------


class TestCancelJob:
    async def test_success(self, ctx, mock_client):
        result = await cancel_job(ctx, task_id="J:100")
        assert "cancelled" in result.lower()
        mock_client.taskactions_stop.assert_awaited_with("J:100", "Cancelled via MCP")

    async def test_custom_reason(self, ctx, mock_client):
        result = await cancel_job(ctx, task_id="RS:4321", reason="No longer needed")
        assert "No longer needed" in result
        mock_client.taskactions_stop.assert_awaited_with("RS:4321", "No longer needed")

    async def test_invalid_id(self, ctx):
        result = await cancel_job(ctx, task_id="bogus")
        assert "Error" in result

    async def test_error(self, ctx, mock_client):
        mock_client.taskactions_stop = AsyncMock(side_effect=BeakerError("denied"))
        result = await cancel_job(ctx, task_id="J:1")
        assert "Error" in result


# ---------------------------------------------------------------------------
# extend_watchdog
# ---------------------------------------------------------------------------


class TestExtendWatchdog:
    async def test_success(self, ctx, mock_client):
        result = await extend_watchdog(ctx, task_id=99999, seconds=3600)
        assert "extended" in result.lower()
        assert "99999" in result
        assert "1.0 hours" in result
        mock_client.recipes_tasks_extend.assert_awaited_with(99999, 3600)

    async def test_zero_seconds(self, ctx):
        result = await extend_watchdog(ctx, task_id=1, seconds=0)
        assert "Error" in result
        assert "positive" in result

    async def test_negative_seconds(self, ctx):
        result = await extend_watchdog(ctx, task_id=1, seconds=-10)
        assert "Error" in result

    async def test_error(self, ctx, mock_client):
        mock_client.recipes_tasks_extend = AsyncMock(side_effect=BeakerError("nope"))
        result = await extend_watchdog(ctx, task_id=1, seconds=100)
        assert "Error" in result


# ---------------------------------------------------------------------------
# set_job_response
# ---------------------------------------------------------------------------


class TestSetJobResponse:
    async def test_ack(self, ctx, mock_client):
        result = await set_job_response(ctx, task_id="RS:4321", response="ack")
        assert "ack" in result
        mock_client.jobs_set_response.assert_awaited_with("RS:4321", "ack")

    async def test_nak(self, ctx, mock_client):
        result = await set_job_response(ctx, task_id="J:100", response="nak")
        assert "nak" in result

    async def test_invalid_response(self, ctx):
        result = await set_job_response(ctx, task_id="J:100", response="maybe")
        assert "Error" in result
        assert "Invalid response" in result

    async def test_invalid_id(self, ctx):
        result = await set_job_response(ctx, task_id="xyz", response="ack")
        assert "Error" in result

    async def test_error(self, ctx, mock_client):
        mock_client.jobs_set_response = AsyncMock(side_effect=BeakerError("denied"))
        result = await set_job_response(ctx, task_id="J:1", response="ack")
        assert "Error" in result


# ---------------------------------------------------------------------------
# watch_job
# ---------------------------------------------------------------------------


class TestWatchJob:
    async def test_completed_pass(self, ctx, mock_client):
        """Already-finished successful job should return diagnosis without retry."""
        mock_client.rest_get_json = AsyncMock(return_value={
            "id": 100, "status": "Completed", "result": "Pass",
            "whiteboard": "Test", "is_finished": True, "submitted_time": "2026-03-12",
            "owner": {"user_name": "testuser"}, "recipesets": [],
        })
        result = await watch_job(ctx, job_id="100", poll_interval=0)
        assert "J:100" in result
        assert "successfully" in result.lower() or "no failure" in result.lower()

    async def test_not_found(self, ctx, mock_client):
        mock_client.rest_get_json = AsyncMock(side_effect=BeakerNotFoundError("gone"))
        result = await watch_job(ctx, job_id="999", poll_interval=0)
        assert "not found" in result.lower()

    async def test_invalid_id(self, ctx):
        result = await watch_job(ctx, job_id="xyz")
        assert "Error" in result

    async def test_failed_job_no_auto_fix(self, ctx, mock_client):
        """Failed job with no corrected XML should stop."""
        mock_client.rest_get_json = AsyncMock(return_value={
            "id": 100, "status": "Aborted", "result": "Fail",
            "whiteboard": "Test", "is_finished": True, "submitted_time": "2026-03-12",
            "owner": {"user_name": "testuser"}, "recipesets": [],
        })
        with patch(
            "mcp_beaker.servers.jobs.attempt_auto_fix",
            new_callable=AsyncMock,
            return_value=("Analysis text here", None),
        ):
            result = await watch_job(ctx, job_id="100", poll_interval=0)
        assert "Analysis text here" in result
        assert "No automatic correction" in result
