"""Beaker API client wrapping XML-RPC and REST endpoints.

Handles cookie-based session management, dual auth (Kerberos via bkr CLI
and password via XML-RPC), and SSL configuration.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import xmlrpc.client
from typing import Any

import httpx

from mcp_beaker.config import BeakerConfig
from mcp_beaker.exceptions import (
    BeakerAuthenticationError,
    BeakerConfigError,
    BeakerConnectionError,
    BeakerNotFoundError,
    BeakerXMLRPCError,
)

logger = logging.getLogger("mcp-beaker")


# ---------------------------------------------------------------------------
# XML-RPC cookie transport
# ---------------------------------------------------------------------------


class CookieTransport(xmlrpc.client.SafeTransport):
    """XML-RPC transport that persists cookies across calls.

    Beaker uses HTTP cookies to track authenticated sessions, so cookies
    returned by ``auth.login_password()`` must be forwarded on subsequent
    calls.
    """

    def __init__(self, ssl_context: ssl.SSLContext | None = None) -> None:
        super().__init__(context=ssl_context)
        self._cookies: list[str] = []

    def send_headers(self, connection: Any, headers: Any) -> None:
        if self._cookies:
            connection.putheader("Cookie", "; ".join(self._cookies))
        super().send_headers(connection, headers)

    def parse_response(self, response: Any) -> Any:
        for header in response.msg.get_all("Set-Cookie") or []:
            cookie = header.split(";", 1)[0]
            if cookie and cookie not in self._cookies:
                self._cookies.append(cookie)
        return super().parse_response(response)


# ---------------------------------------------------------------------------
# Beaker client
# ---------------------------------------------------------------------------


class BeakerClient:
    """High-level client for the Beaker XML-RPC and REST APIs.

    Instantiated once per server lifespan and shared across tool calls
    via dependency injection.
    """

    def __init__(self, config: BeakerConfig) -> None:
        if not config.url:
            raise BeakerConfigError(
                "No Beaker URL configured. Set the BEAKER_URL environment "
                "variable or pass --beaker-url."
            )
        self.config = config
        self._ssl_context = config.make_ssl_context()
        self._proxy: xmlrpc.client.ServerProxy | None = None
        self._authenticated = False

    # -- XML-RPC ------------------------------------------------------------

    def _get_proxy(self) -> xmlrpc.client.ServerProxy:
        if self._proxy is None:
            transport = CookieTransport(ssl_context=self._ssl_context)
            self._proxy = xmlrpc.client.ServerProxy(self.config.rpc_url, transport=transport)
        return self._proxy

    def _ensure_password_auth(self) -> None:
        """Authenticate with username/password if not already done."""
        if self._authenticated:
            return
        proxy = self._get_proxy()
        if not self.config.username or not self.config.password:
            raise BeakerAuthenticationError(
                "Password auth requires BEAKER_USERNAME and BEAKER_PASSWORD environment variables."
            )
        try:
            proxy.auth.login_password(self.config.username, self.config.password)
        except xmlrpc.client.Fault as exc:
            raise BeakerAuthenticationError(f"Beaker login failed: {exc.faultString}") from exc
        except Exception as exc:
            raise BeakerConnectionError(
                f"Could not connect to Beaker at {self.config.url}: {exc}"
            ) from exc
        self._authenticated = True

    async def call_xmlrpc(self, method: str, *args: Any) -> Any:
        """Call a Beaker XML-RPC method, handling auth and threading.

        For unauthenticated calls (e.g. ``distrotrees.filter``), the proxy
        is used directly.  For authenticated calls, ``_ensure_password_auth``
        is invoked first when using password auth.
        """
        proxy = self._get_proxy()

        def _call() -> Any:
            obj: Any = proxy
            for part in method.split("."):
                obj = getattr(obj, part)
            return obj(*args)

        try:
            return await asyncio.to_thread(_call)
        except xmlrpc.client.Fault as exc:
            raise BeakerXMLRPCError(exc.faultCode, exc.faultString) from exc
        except ConnectionError as exc:
            raise BeakerConnectionError(
                f"Could not connect to Beaker at {self.config.url}: {exc}"
            ) from exc

    async def call_xmlrpc_authenticated(self, method: str, *args: Any) -> Any:
        """Call an XML-RPC method that requires authentication."""
        if self.config.auth_method == "password":
            await asyncio.to_thread(self._ensure_password_auth)
        return await self.call_xmlrpc(method, *args)

    # -- REST / HTTP --------------------------------------------------------

    async def rest_get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        """Make an authenticated GET request to the Beaker REST API."""
        url = f"{self.config.url}{path}"
        verify: bool | ssl.SSLContext = (
            self._ssl_context if self._ssl_context is not None else self.config.ssl_verify
        )
        async with httpx.AsyncClient(verify=verify) as client:
            try:
                response = await client.get(url, headers=headers, params=params, timeout=timeout)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 404:
                    raise BeakerNotFoundError(f"Not found: {path}") from exc
                if status in (401, 403):
                    raise BeakerAuthenticationError(
                        f"Authentication failed for {path} (HTTP {status})"
                    ) from exc
                raise
            except httpx.ConnectError as exc:
                raise BeakerConnectionError(
                    f"Could not connect to Beaker at {self.config.url}: {exc}"
                ) from exc

    async def rest_get_json(
        self,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """GET a JSON response from the Beaker REST API."""
        headers = kwargs.pop("headers", {})
        headers["Accept"] = "application/json"
        response = await self.rest_get(path, headers=headers, **kwargs)
        return response.json()

    async def rest_get_text(
        self,
        path: str,
        **kwargs: Any,
    ) -> str:
        """GET a text response from the Beaker REST API."""
        response = await self.rest_get(path, **kwargs)
        return response.text

    # -- Convenience wrappers for specific API calls -----------------------

    async def whoami(self) -> dict[str, Any]:
        await asyncio.to_thread(self._ensure_password_auth)
        return await self.call_xmlrpc("auth.who_am_i")

    async def lab_controllers(self) -> list[str]:
        return await self.call_xmlrpc("lab_controllers")

    async def jobs_filter(self, filters: dict[str, Any]) -> list[str]:
        return await self.call_xmlrpc("jobs.filter", filters)

    async def jobs_upload(self, job_xml: str) -> str:
        return await self.call_xmlrpc_authenticated("jobs.upload", job_xml)

    async def jobs_set_response(self, taskid: str, response: str) -> Any:
        return await self.call_xmlrpc_authenticated("jobs.set_response", taskid, response)

    async def taskactions_task_info(self, taskid: str) -> dict[str, Any]:
        return await self.call_xmlrpc("taskactions.task_info", taskid)

    async def taskactions_to_xml(
        self,
        taskid: str,
        clone: bool = False,
        include_logs: bool = True,
    ) -> str:
        return await self.call_xmlrpc("taskactions.to_xml", taskid, clone, True, include_logs)

    async def taskactions_files(self, taskid: str) -> list[dict[str, Any]]:
        return await self.call_xmlrpc("taskactions.files", taskid)

    async def taskactions_stop(self, taskid: str, msg: str) -> Any:
        return await self.call_xmlrpc_authenticated("taskactions.stop", taskid, "cancel", msg)

    async def systems_reserve(self, fqdn: str) -> Any:
        return await self.call_xmlrpc_authenticated("systems.reserve", fqdn)

    async def systems_release(self, fqdn: str) -> Any:
        return await self.call_xmlrpc_authenticated("systems.release", fqdn)

    async def systems_power(self, action: str, fqdn: str, force: bool = False) -> Any:
        return await self.call_xmlrpc_authenticated("systems.power", action, fqdn, False, force)

    async def systems_provision(
        self,
        fqdn: str,
        distro_tree_id: int,
        ks_meta: str = "",
        kernel_options: str = "",
        kernel_options_post: str = "",
        kickstart: str = "",
        reboot: bool = True,
    ) -> Any:
        return await self.call_xmlrpc_authenticated(
            "systems.provision",
            fqdn,
            distro_tree_id,
            ks_meta,
            kernel_options,
            kernel_options_post,
            kickstart,
            reboot,
        )

    async def systems_history(self, fqdn: str, since: str | None = None) -> list[dict[str, Any]]:
        args: list[Any] = [fqdn]
        if since is not None:
            args.append(since)
        return await self.call_xmlrpc("systems.history", *args)

    async def systems_get_osmajor_arches(
        self, fqdn: str, tags: list[str] | None = None
    ) -> dict[str, list[str]]:
        args: list[Any] = [fqdn]
        if tags is not None:
            args.append(tags)
        return await self.call_xmlrpc("systems.get_osmajor_arches", *args)

    async def distrotrees_filter(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.call_xmlrpc("distrotrees.filter", filters)

    async def distros_get_osmajors(self, tags: list[str] | None = None) -> list[str]:
        if tags is not None:
            return await self.call_xmlrpc("distros.get_osmajors", tags)
        return await self.call_xmlrpc("distros.get_osmajors")

    async def tasks_filter(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.call_xmlrpc("tasks.filter", filters)

    async def recipes_tasks_extend(self, task_id: int, kill_time: int) -> Any:
        return await self.call_xmlrpc_authenticated("recipes.tasks.extend", task_id, kill_time)
