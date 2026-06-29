# Changelog

All notable changes to this project will be documented in this file.

## [0.5.0] - 2026-06-29

### Added
- `search_systems` tool — search Beaker systems by CPU vendor, model, family, architecture, memory, pool, and other hardware attributes
- `_build_search_params` helper to map filter dicts to Beaker's `systemsearch-N.*` query parameters
- Support for comparison operators (`>=`, `<=`) in numeric filters (cores, memory)
- 11 new tests covering search parameter building, CPU/pool/arch/memory searches, edge cases

## [0.4.0] - 2026-06-29

### Added
- CPU details in `get_system_details` output: vendor, model name, family, model, stepping, speed, processors, cores, sockets, hyper-threading, and CPU flags
- Pool membership in `get_system_details` output: list of Beaker pool names the system belongs to
- 12 new fields on `SystemInfo` model matching the Beaker REST API contract
- Test assertions for all new CPU and pool fields

### Fixed
- Test mock data now uses correct `arches` field name (was `arch`, silently ignored by Pydantic)

### Contributors
- @tasharma1

## [0.3.1] - 2026-04-28

### Fixed
- REST POST/PATCH calls (`loan_system`, `return_loan`) now trigger SPNEGO authentication before making the request, fixing 401 errors when using the `http` Kerberos backend

## [0.3.0] - 2026-04-28

### Added
- `loan_system` tool -- grant a loan for a Beaker system to a specific user (or yourself)
- `return_loan` tool -- return the current loan on a Beaker system
- `BeakerClient.systems_loan_grant()` and `systems_loan_return()` convenience methods
- REST API support: `POST /systems/<fqdn>/loans/` and `PATCH /systems/<fqdn>/loans/+current`
- `bkr loan-grant` and `bkr loan-return` CLI wrappers in `bkr_cli.py`
- `rest_post_json()` and `rest_patch_json()` HTTP helpers on `BeakerClient`
- 8 new tests for loan tools (recipient, self-loan, comment, error handling)

## [0.2.3] - 2026-03-23

### Added
- Generic cross-platform container support -- zero volume mounts required
- `entrypoint.sh` runs `kinit` inside the container from `KRB5_PRINCIPAL` and `KRB5_PASSWORD` env vars
- Built-in DNS-discovery `krb5.conf` -- no host Kerberos config needed
- Keytab support: mount a `.keytab` file to `/etc/krb5.keytab` for passwordless auth

### Changed
- Container config simplified from 6 volume mounts to zero
- Updated README, example configs, and CHANGELOG for generic container usage

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
