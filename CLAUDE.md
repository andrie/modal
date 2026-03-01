# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

modal-hcc is a Modal.com serverless application providing real-time paddling conditions for Hampton Canoe Club on the River Thames. It integrates river flow/level data (Environment Agency API), weather forecasts (Met Office API), water temperature, sunrise times, and AI-generated guidance (Claude) to help paddlers assess safety conditions.

## Key Commands

```bash
# Run the full app (triggers all cache functions)
uv run modal run ./new-app.py

# Serve locally for development
uv run modal serve ./new-app.py

# Deploy to production
uv run modal deploy ./new-app.py

# Selective execution
uv run modal run new-app.py --update-flow --no-update-weather --no-guidance
uv run modal run new-app.py --no-update-flow --update-weather --guidance
uv run modal run new-app.py --no-update-flow --no-update-weather --guidance
```

There is no test suite, linter, or CI/CD pipeline.

## Dependency Management

Dependencies are managed with `uv`. The `pyproject.toml` declares all dependencies, including git-sourced packages via PEP 508 direct references (e.g., `ea-rivers @ git+https://...`). The `uv.lock` file pins exact versions.

```bash
# Sync dependencies (install from lock file)
uv sync

# Add a new dependency
uv add <package>
```

The Modal container image installs from `pyproject.toml` via `pip_install_from_pyproject()`, which passes the PEP 508 specs directly to pip. This means git dependencies must use the `package @ git+https://...` syntax (not `[tool.uv.sources]`), since pip does not understand uv-specific source overrides.

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation including system diagrams, data flow, external APIs, and error handling patterns.

Key points:
- Two scheduled Modal functions (`cache_flow` hourly, `cache_weather` every 6h) populate a shared `Modal Dict` cache
- A FastAPI endpoint (`conditions()`) serves cached data to a JS frontend
- Two container images: `minimal_image` (endpoint only) and `conditions_image` (full deps from `pyproject.toml`), both pinned to Python 3.12
- Git-sourced packages: `ea-rivers`, `hcc` (from `thames_river_conditions` repo), `chatlas`
- Note: the `thames_river_conditions` repo produces a package named `hcc`
- Production endpoint: `https://andrie--conditions.modal.run/`
