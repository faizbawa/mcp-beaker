# mcp-beaker

![PyPI Version](https://img.shields.io/pypi/v/mcp-beaker)
[![PyPI Downloads](https://static.pepy.tech/badge/mcp-beaker)](https://pepy.tech/projects/mcp-beaker)
[![CI](https://github.com/faizbawa/mcp-beaker/actions/workflows/ci.yml/badge.svg)](https://github.com/faizbawa/mcp-beaker/actions/workflows/ci.yml)
![License](https://img.shields.io/github/license/faizbawa/mcp-beaker)
![Python](https://img.shields.io/pypi/pyversions/mcp-beaker)

MCP server for [Beaker](https://beaker-project.org/) lab automation -- system provisioning, job management, distro discovery, and failure diagnosis.

Works with any Beaker server instance. Built on [FastMCP v3](https://gofastmcp.com/) and designed for use with AI coding assistants (Cursor, Claude Desktop, etc.).

## Features

- **23 tools** covering the full Beaker lifecycle: systems, jobs, distros, tasks
- **Flexible auth**: Kerberos (native GSSAPI/SPNEGO or `bkr` CLI fallback) and password (XML-RPC)
- **Job XML validation**: auto-fills missing fields, infers distro families
- **Failure diagnosis**: deep analysis with auto-retry on correctable failures
- **10 documentation topics** exposed as MCP resources
- **2 workflow prompts** for common tasks (reserve system, diagnose job)
- **Generic**: works with any Beaker URL, configurable SSL/CA settings

## Installation

### Container (recommended)

The container image bundles `krb5-devel` and `gssapi` so there are no host
dependencies beyond `podman` (or `docker`) and a valid Kerberos ticket.

```bash
# Pull the pre-built image from GHCR
podman pull ghcr.io/faizbawa/mcp-beaker:latest

# Or build locally from the repo
podman build -t mcp-beaker:latest -f Containerfile .
```

### Pip / uvx

```bash
# Using uv (recommended)
pip install uv
uvx mcp-beaker

# Using pip
pip install mcp-beaker
mcp-beaker

# With native Kerberos support (no bkr CLI needed -- requires krb5-devel on host)
pip install mcp-beaker[kerberos]

# Local development
uv run --directory /path/to/mcp-beaker mcp-beaker
```

## Configuration

### Cursor / VS Code

Add to your `.cursor/mcp.json` (or `.vscode/mcp.json`):

#### Container (recommended)

```json
{
  "mcpServers": {
    "beaker": {
      "command": "podman",
      "args": [
        "run", "--rm", "-i", "--pid=host",
        "-v", "/run/.heim_org.h5l.kcm-socket:/run/.heim_org.h5l.kcm-socket",
        "-v", "/etc/krb5.conf:/etc/krb5.conf:ro",
        "-v", "/etc/krb5.conf.d:/etc/krb5.conf.d:ro",
        "-v", "/etc/crypto-policies:/etc/crypto-policies:ro",
        "-v", "/etc/pki:/etc/pki:ro",
        "-v", "/var/lib/sss/pubconf/krb5.include.d:/var/lib/sss/pubconf/krb5.include.d:ro",
        "-e", "BEAKER_URL=https://beaker.example.com",
        "-e", "BEAKER_AUTH_METHOD=kerberos",
        "-e", "BEAKER_KERBEROS_BACKEND=http",
        "-e", "KRB5CCNAME=KCM:",
        "ghcr.io/faizbawa/mcp-beaker:latest"
      ]
    }
  }
}
```

The volume mounts forward the host Kerberos ticket (KCM cache) and TLS
certificates into the container. Run `kinit` on the host before starting.

#### Pip / uvx

```json
{
  "mcpServers": {
    "beaker": {
      "command": "uvx",
      "args": ["mcp-beaker[kerberos]"],
      "env": {
        "BEAKER_URL": "https://beaker.example.com",
        "BEAKER_AUTH_METHOD": "kerberos",
        "BEAKER_KERBEROS_BACKEND": "http"
      }
    }
  }
}
```

### Streamable HTTP mode

```bash
uvx mcp-beaker --transport streamable-http --port 8000
```

```json
{
  "mcpServers": {
    "beaker": {
      "url": "http://localhost:8000/mcp",
      "type": "streamableHttp"
    }
  }
}
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BEAKER_URL` | Yes | -- | Base URL of your Beaker server |
| `BEAKER_AUTH_METHOD` | No | `kerberos` | `kerberos` or `password` |
| `BEAKER_KERBEROS_BACKEND` | No | `http` | `http` (native SPNEGO) or `bkr` (bkr CLI) |
| `BEAKER_USERNAME` | For password auth | -- | Beaker username |
| `BEAKER_PASSWORD` | For password auth | -- | Beaker password |
| `BEAKER_OWNER` | No | `$USER` | Default owner for job queries |
| `BEAKER_SSL_VERIFY` | No | `true` | Verify SSL certificates |
| `BEAKER_CA_CERT` | No | -- | Path to CA certificate bundle |

## CLI Options

```
mcp-beaker [OPTIONS]

Options:
  --transport [stdio|sse|streamable-http]  Transport type (default: stdio)
  --port INTEGER                           Port for HTTP transports (default: 8000)
  --host TEXT                              Host for HTTP transports (default: 0.0.0.0)
  --path TEXT                              Path for streamable-http (default: /mcp)
  --beaker-url TEXT                        Beaker server URL
  --ssl-verify / --no-ssl-verify           Verify SSL certs (default: verify)
  --ca-cert TEXT                           CA certificate bundle path
  --auth-method [kerberos|password]        Authentication method
  --kerberos-backend [http|bkr]            Kerberos backend (default: http)
  --read-only                              Disable all write tools
  --enabled-tools TEXT                     Comma-separated tools to enable
  -v, --verbose                            Increase verbosity (-v info, -vv debug)
  --version                                Show version
  --help                                   Show this message
```

## Tools

### Read Tools (13)

| Tool | Description |
|------|-------------|
| `list_systems` | List systems by availability (all/available/free) |
| `get_system_details` | Hardware specs, ownership, status for a system |
| `get_system_history` | Activity history for a system |
| `get_system_arches` | Supported OS families and architectures |
| `list_jobs` | Filter jobs by owner, status, whiteboard |
| `get_job_status` | Job status with failure diagnosis |
| `get_job_results_xml` | Export job results as XML |
| `get_job_logs` | List log files for a job/recipe/task |
| `list_distro_trees` | Search distros by name, family, arch, tags |
| `list_os_families` | List all known OS families |
| `whoami` | Show authenticated user info |
| `list_lab_controllers` | List all lab controllers |
| `search_tasks` | Search the task library |

### Write Tools (10)

| Tool | Description |
|------|-------------|
| `submit_job` | Submit a job from XML (with validation and auto-fill) |
| `clone_job` | Clone and resubmit an existing job |
| `cancel_job` | Cancel a running/queued job |
| `watch_job` | Poll until completion with failure analysis and auto-retry |
| `reserve_system` | Manually reserve a system |
| `release_system` | Release a manually reserved system |
| `power_system` | Power on/off/reboot a system |
| `provision_system` | Provision a reserved system with a distro |
| `extend_watchdog` | Extend a running task's watchdog timer |
| `set_job_response` | Ack/nak (waive) a recipe set result |

## Authentication

### Kerberos (recommended)

Ensure you have a valid ticket:

```bash
kinit your-username@YOUR.REALM
```

The server supports two Kerberos backends, controlled by `BEAKER_KERBEROS_BACKEND`:

| Value | Backend | Install |
|-------|---------|---------|
| `http` (default) | **Native GSSAPI/SPNEGO** -- lightweight, pip-installable | `pip install mcp-beaker[kerberos]` |
| `bkr` | **`bkr` CLI** subprocesses -- traditional, requires RPM | `yum install beaker-client` |

Both backends use the same Kerberos ticket from `kinit`.

### Password

Set `BEAKER_AUTH_METHOD=password` along with `BEAKER_USERNAME` and `BEAKER_PASSWORD`. The server authenticates via the XML-RPC `auth.login_password()` method. Note: this requires server-side LDAP to be enabled.

## Architecture

```
src/mcp_beaker/
  __init__.py           # Click CLI entry point
  config.py             # BeakerConfig dataclass
  exceptions.py         # Custom exceptions
  client.py             # BeakerClient (XML-RPC + REST)
  models/               # Pydantic response models
  servers/
    __init__.py         # FastMCP server, lifespan, DI helper
    systems.py          # System tools (4 read + 4 write)
    jobs.py             # Job tools (4 read + 6 write)
    distros.py          # Distro tools (2 read)
    tasks.py            # Task tools (1 read)
    general.py          # General tools (2 read)
    prompts.py          # Workflow prompt templates
    resources.py        # Beaker documentation resources
  utils/
    xml_validation.py   # Job XML validation/auto-fill
    diagnosis.py        # Failure analysis engine
    formatting.py       # Human-readable formatters
    bkr_cli.py          # bkr CLI helpers
    parsing.py          # ID parsing utilities
```

## Development

```bash
cd mcp-beaker
uv sync --dev
uv run pytest
uv run ruff check src/
```

## License

MIT
