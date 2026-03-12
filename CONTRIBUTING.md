# Contributing to mcp-beaker

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/faizbawa/mcp-beaker.git
cd mcp-beaker
uv sync --dev
```

## Running Tests

```bash
uv run pytest tests/ -v
```

## Linting

```bash
uv run ruff check src/
uv run ruff format --check src/
```

## Making Changes

1. **Fork** the repository and create a branch from `master`
2. **Write tests** for any new tools or changed behavior
3. **Run tests and linting** before submitting
4. **Keep commits focused** -- one logical change per commit
5. **Open a pull request** with a clear description of the change

## Project Structure

```
src/mcp_beaker/
  __init__.py           # CLI entry point
  config.py             # BeakerConfig dataclass
  exceptions.py         # Custom exception hierarchy
  client.py             # BeakerClient (XML-RPC + REST)
  models/               # Pydantic response models
  servers/
    __init__.py         # FastMCP server, lifespan, DI
    systems.py          # System tools (4 read + 4 write)
    jobs.py             # Job tools (5 read + 5 write)
    distros.py          # Distro tools (2 read)
    tasks.py            # Task tools (1 read)
    general.py          # General tools (2 read)
    prompts.py          # Workflow prompt templates
    resources.py        # Documentation resources
  utils/
    xml_validation.py   # Job XML validation/auto-fill
    diagnosis.py        # Failure analysis engine
    formatting.py       # Human-readable formatters
    bkr_cli.py          # bkr CLI wrappers
    parsing.py          # ID parsing utilities
tests/
  conftest.py           # Shared fixtures and mocks
  test_tools_*.py       # Tool unit tests
```

## Adding a New Tool

1. Add the client method in `client.py`
2. Add the tool function in the appropriate `servers/*.py` module
3. Add a Pydantic model in `models/` if the response needs one
4. Add a formatter in `utils/formatting.py`
5. Write tests in `tests/test_tools_*.py`
6. Update `README.md` with the new tool

## Code Style

- Line length: 100 characters
- Formatter: ruff
- Type hints on all public functions
- Docstrings on all tools (they become MCP tool descriptions)
- No hardcoded Beaker URLs or credentials

## Reporting Issues

Use [GitHub Issues](https://github.com/faizbawa/mcp-beaker/issues) with the appropriate template.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
