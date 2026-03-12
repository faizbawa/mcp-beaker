"""MCP Beaker Server -- Beaker lab automation for AI agents.

Entry point for the ``mcp-beaker`` CLI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

try:
    __version__ = version("mcp-beaker")
except PackageNotFoundError:
    __version__ = "0.0.0"

logger = logging.getLogger("mcp-beaker")


def _setup_logging(level: int, stream: object = None) -> logging.Logger:
    if stream is None:
        stream = sys.stderr
    root = logging.getLogger("mcp-beaker")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(stream)
        handler.setLevel(level)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(fmt)
        root.addHandler(handler)
    return root


async def _watch_parent_exit(stop_event: threading.Event) -> None:
    parent_pid = os.getppid()
    loop = asyncio.get_running_loop()

    def _poll_parent_alive() -> None:
        while not stop_event.wait(5):
            current_ppid = os.getppid()
            if current_ppid != parent_pid:
                logger.info(
                    "Parent process %d exited (reparented to %d). Shutting down.",
                    parent_pid,
                    current_ppid,
                )
                return

    await loop.run_in_executor(None, _poll_parent_alive)


async def _run_stdio_with_guard(run_kwargs: dict[str, object]) -> None:
    from mcp_beaker.servers import mcp as beaker_mcp

    parent_watch_stop = threading.Event()
    server_task = asyncio.create_task(beaker_mcp.run_async(**run_kwargs))
    parent_task = asyncio.create_task(_watch_parent_exit(parent_watch_stop))

    done, pending = await asyncio.wait(
        {server_task, parent_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    parent_watch_stop.set()

    if parent_task in done and not server_task.done():
        logger.info("Parent process exited. Shutting down STDIO server.")
        server_task.cancel()

    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    if server_task.done():
        results = await asyncio.gather(server_task, return_exceptions=True)
        if (
            results
            and isinstance(results[0], Exception)
            and not isinstance(results[0], asyncio.CancelledError)
        ):
            raise results[0]


import click


@click.version_option(__version__, prog_name="mcp-beaker")
@click.command()
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v info, -vv debug)")
@click.option("--env-file", type=click.Path(exists=True, dir_okay=False), help="Path to .env file")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    default="stdio",
    help="Transport type (default: stdio)",
)
@click.option("--port", default=8000, help="Port for HTTP transports (default: 8000)")
@click.option("--host", default="0.0.0.0", help="Host for HTTP transports (default: 0.0.0.0)")
@click.option("--path", default="/mcp", help="Path for streamable-http (default: /mcp)")
@click.option("--beaker-url", help="Beaker server URL (overrides BEAKER_URL env var)")
@click.option(
    "--ssl-verify/--no-ssl-verify",
    default=True,
    help="Verify SSL certificates (default: verify)",
)
@click.option("--ca-cert", help="Path to CA certificate bundle")
@click.option(
    "--auth-method",
    type=click.Choice(["kerberos", "password"]),
    help="Authentication method",
)
@click.option("--read-only", is_flag=True, help="Disable all write tools")
@click.option(
    "--enabled-tools",
    help="Comma-separated list of tools to enable (all if not specified)",
)
def main(
    verbose: int,
    env_file: str | None,
    transport: str,
    port: int,
    host: str,
    path: str | None,
    beaker_url: str | None,
    ssl_verify: bool,
    ca_cert: str | None,
    auth_method: str | None,
    read_only: bool,
    enabled_tools: str | None,
) -> None:
    """MCP Beaker Server -- Beaker lab automation for AI agents.

    Provides tools for managing Beaker systems, jobs, distros, and tasks
    via the Model Context Protocol. Supports both Kerberos and password
    authentication against any Beaker server instance.
    """
    # Logging
    if verbose >= 2:
        log_level = logging.DEBUG
    elif verbose == 1:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    _setup_logging(log_level)

    # Environment
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)

    # CLI overrides -> env vars
    click_ctx = click.get_current_context(silent=True)

    def _was_provided(param: str) -> bool:
        if click_ctx is None:
            return False
        src = click_ctx.get_parameter_source(param)
        default_sources = (
            click.core.ParameterSource.DEFAULT,
            click.core.ParameterSource.DEFAULT_MAP,
        )
        return src not in default_sources

    if _was_provided("beaker_url") and beaker_url:
        os.environ["BEAKER_URL"] = beaker_url
    if _was_provided("ssl_verify"):
        os.environ["BEAKER_SSL_VERIFY"] = str(ssl_verify).lower()
    if _was_provided("ca_cert") and ca_cert:
        os.environ["BEAKER_CA_CERT"] = ca_cert
    if _was_provided("auth_method") and auth_method:
        os.environ["BEAKER_AUTH_METHOD"] = auth_method
    if _was_provided("read_only"):
        os.environ["BEAKER_READ_ONLY"] = str(read_only).lower()
    if _was_provided("enabled_tools") and enabled_tools:
        os.environ["BEAKER_ENABLED_TOOLS"] = enabled_tools

    # Transport resolution: env var -> CLI flag -> default
    final_transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if _was_provided("transport"):
        final_transport = transport

    final_port = int(os.getenv("MCP_PORT", str(port)))
    if _was_provided("port"):
        final_port = port

    final_host = os.getenv("MCP_HOST", host)
    if _was_provided("host"):
        final_host = host

    final_path = os.getenv("MCP_PATH", path)
    if _was_provided("path"):
        final_path = path

    from mcp_beaker.servers import mcp as beaker_mcp

    run_kwargs: dict[str, object] = {
        "transport": final_transport,
    }

    if final_transport == "stdio":
        logger.info("Starting Beaker MCP server with STDIO transport.")
    elif final_transport in ("sse", "streamable-http"):
        run_kwargs["host"] = final_host
        run_kwargs["port"] = final_port
        if final_path:
            run_kwargs["path"] = final_path
        logger.info(
            "Starting Beaker MCP server with %s transport on http://%s:%d%s",
            final_transport.upper(),
            final_host,
            final_port,
            final_path or "/mcp",
        )

    try:
        if final_transport == "stdio":
            asyncio.run(_run_stdio_with_guard(run_kwargs))
        else:
            asyncio.run(beaker_mcp.run_async(**run_kwargs))
    except (KeyboardInterrupt, SystemExit):
        logger.info("Server shutdown initiated.")
    except Exception as exc:
        logger.error("Server error: %s", exc, exc_info=True)
        sys.exit(1)


__all__ = ["main", "__version__"]

if __name__ == "__main__":
    main()
