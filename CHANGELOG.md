# Changelog

All notable changes to this project will be documented in this file.

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
