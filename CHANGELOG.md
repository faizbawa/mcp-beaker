# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] - 2026-03-23

### Added
- Pre-built container image on GHCR (`ghcr.io/faizbawa/mcp-beaker`)
- GitHub Actions workflow to publish container image on every release
- Multi-stage Containerfile to strip compiler toolchain from final image

## [0.2.0] - 2026-03-23

### Added
- Native GSSAPI/SPNEGO Kerberos authentication -- no `bkr` CLI required
- `BEAKER_KERBEROS_BACKEND` env var (`http` default, `bkr` fallback)
- `--kerberos-backend` CLI option
- `gssapi` as optional dependency (`pip install mcp-beaker[kerberos]`)
- Session cookie injection into REST API calls for authenticated endpoints
- 17 new unit tests for auth strategies (SPNEGO, bkr routing, cookie injection)
- `Containerfile` for building a batteries-included OCI image (`podman`/`docker`)
- Pre-built container image published to `ghcr.io/faizbawa/mcp-beaker` on every release
- Multi-stage build to strip compiler toolchain from final image
- Container documentation with KCM Kerberos ticket forwarding via volume mounts

### Changed
- `_use_bkr` routing now driven by `kerberos_backend` config instead of auto-detection
- Job submission in `servers/jobs.py` uses `client._use_bkr` instead of standalone `is_bkr_available()`
- XML-RPC connection retry re-authenticates using the correct backend

## [0.1.1] - 2026-03-12

### Added
- 102 unit tests covering all 23 MCP tools
- CI workflow (Python 3.11, 3.12, 3.13)
- Publish workflow with PyPI trusted publishing
- LICENSE file (MIT)
- README badges (PyPI version, downloads, CI, license, Python versions)
- CONTRIBUTING.md, CHANGELOG.md
- GitHub issue and PR templates

### Fixed
- Pydantic model validation for nullable fields from Beaker REST API
- Integer-to-string coercion for job/recipe/task IDs
- Stale XML-RPC connection handling with automatic retry
- `list_jobs` fallback to job ID list when REST detail fetch fails
- XML-RPC `DateTime` object stringification in `get_system_history`
- `systems_get_osmajor_arches` routed through authenticated XML-RPC

## [0.1.0] - 2026-03-12

### Added
- Initial release with 23 MCP tools (13 read, 10 write)
- Dual authentication: Kerberos (via `bkr` CLI) and password (via XML-RPC)
- Job XML validation with auto-fill for missing fields
- Failure diagnosis engine with auto-retry
- 10 documentation topics as MCP resources
- 2 workflow prompts (reserve system, diagnose job)
- CLI with stdio, SSE, and streamable-http transport support
