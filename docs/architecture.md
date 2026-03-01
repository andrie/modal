# Architecture

## Overview

modal-hcc is a serverless application on [Modal.com](https://modal.com) that provides real-time paddling conditions for Hampton Canoe Club on the River Thames. Two scheduled functions collect data from external APIs, store it in a shared cache, and a FastAPI endpoint serves it to a JavaScript frontend.

## System diagram

```
                        Scheduled (hourly)              Scheduled (every 6h)
                       ┌──────────────┐                ┌──────────────────┐
                       │  cache_flow  │                │  cache_weather   │
                       └──────┬───────┘                └────────┬─────────┘
                              │                                 │
          ┌───────────────────┼──────────┐         ┌────────────┼──────────┐
          ▼                   ▼          ▼         ▼            ▼          ▼
   EA Flood API       Sunrise calc   Lock board  Met Office  Claude API  Water temp
   (flow + level)     (astral/hcc)   scraper     API         (chatlas)   scraper
          │                   │          │         │            │          │
          └───────────────────┴──────────┴─────────┴────────────┴──────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │  Modal Dict cache  │
                               │  (hcc-modal-dict)  │
                               └─────────┬─────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │  conditions()      │
                               │  FastAPI endpoint   │
                               │  GET /conditions    │
                               └─────────┬─────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │  JS frontend       │
                               │  (Quarto + Grid.js │
                               │   + Plotly)         │
                               └───────────────────┘
```

## Backend (`new-app.py`)

### Container images

Two Modal container images are defined, both pinned to Python 3.12:

- **`minimal_image`** — Debian slim with `pandas` and `requests`. Used by the `conditions()` endpoint which only reads from the cache.
- **`conditions_image`** — Full dependency set installed from `pyproject.toml` (including git-sourced packages). Used by the scheduled functions that fetch external data and call the Claude API. Includes `/system_prompt.md` copied into the container.

### Scheduled functions

**`cache_flow()`** — runs every hour

Populates these keys in the Modal Dict cache:
- `flow_kingston`, `flow_walton` — river flow time series (7 days, 15-min intervals) from the EA flood monitoring API
- `level_sunbury`, `level_molesey` — river level time series from the EA API
- `sunrise` — sunrise/sunset times computed via the `hcc` package
- `lockboard` — lock board conditions scraped from the EA website (rows 42-45, covering the Shepperton/Sunbury/Molesey reach)
- `water_temperature` — scraped from `dl1.findlays.net`

After caching, calls `update_hcc_dict()` to rebuild aggregate views.

**`cache_weather()`** — runs every 6 hours

Populates these keys:
- `weather` — 3-hourly Met Office forecast for coordinates 51.41, -0.36 (requires `MET-OFFICE` secret)
- `ai_guidance` — AI-generated paddling guidance from Claude (via `get_gpt_summary()`)

After caching weather, calls `update_hcc_dict()` then triggers AI guidance generation.

### AI guidance pipeline (`get_gpt_summary`)

1. Reads `/system_prompt.md` from the container filesystem
2. Fetches current `hcc_terse` conditions from the cache
3. Processes weather data via `get_hcc_conditions()` (computes mean temperature, converts wind speed to km/h)
4. Appends conditions JSON to the system prompt
5. Sends to Claude Haiku 4.5 via `chatlas.ChatAnthropic`
6. Returns the generated guidance text

Requires the `ANTHROPIC_API_KEY` secret.

### Cache aggregation (`update_hcc_dict`)

Builds three aggregate views from individual cache keys:

| Key | Contents |
|-----|----------|
| `hcc_terse` | Latest flow value, water temp, sunrise, lock boards, weather |
| `hcc_summary` | Terse + full Walton flow series + Sunbury level series |
| `hcc_all` | Summary + Kingston flow + Molesey level |

### FastAPI endpoint (`conditions`)

`GET /conditions?metric=<metric>&station=<station>`

Runs on `minimal_image`. Reads directly from the Modal Dict cache. Supported `metric` values: `flow`, `level`, `sunrise`, `boards`, `weather`, `ai_guidance`, `hcc_terse`, `hcc_summary`, `hcc_all`.

Production URL: `https://andrie--conditions.modal.run/`

### Local entrypoint (`run`)

`modal run new-app.py` accepts flags to selectively trigger cache functions:
- `--update-flow` / `--no-update-flow`
- `--update-weather` / `--no-update-weather`
- `--guidance` / `--no-guidance`

## Frontend

### Quarto document (`streaming-conditions.qmd`)

Rendered HTML page deployed on Posit Connect Cloud. Loads Grid.js (tables), Plotly (charts), and weather icon fonts. All data fetching and rendering is handled client-side by `js/modal.js`.

### JavaScript (`js/modal.js`)

On page load:
1. Fetches `hcc_all` aggregate from the endpoint
2. Populates localStorage cache (15-min expiry) for each data component
3. Renders sections in sequence: sunrise times, river conditions, flow charts, AI summary, lock levels, weather forecast

Key rendering functions:
- `displaySunTimes()` — Grid.js table
- `displayRiverConditions()` — Grid.js table (lock board conditions)
- `updateFlowRate(station)` — Plotly line chart
- `updateLockLevel(station)` — Plotly line chart
- `updateWeather()` — Grid.js transposed table with weather icons
- `displayAIsummary()` — raw HTML from AI-generated markdown

## External data sources

| Source | API | Data | Used by |
|--------|-----|------|---------|
| Environment Agency | `environment.data.gov.uk/flood-monitoring` | Flow (Kingston, Walton), Level (Sunbury, Molesey) | `cache_flow` via `ea_rivers` |
| Met Office | DataHub API | 3-hourly weather forecast | `cache_weather` via `hcc.metoffice` |
| Findlays | `dl1.findlays.net/show/temp/thames1` | Water temperature (scrape) | `cache_flow` |
| EA lock boards | Scraped via `hcc.scrape_conditions()` | Lock gate conditions | `cache_flow` |
| Anthropic | Claude API | AI paddling guidance | `get_gpt_summary` via `chatlas` |

## Git-sourced dependencies

These packages are not on PyPI and are installed from GitHub:

| Package | Import name | Repository | Purpose |
|---------|-------------|------------|---------|
| `ea-rivers` | `ea_rivers` | `DavidASmith/ea-rivers` | EA flood monitoring API wrapper |
| `hcc` | `hcc` | `andrie/thames_river_conditions` | Thames conditions: sunrise, lock board scraping, Met Office client |
| `chatlas` | `chatlas` | `cpsievert/chatlas` | Python chat interface for LLM APIs |

Note: the `thames_river_conditions` repo produces a package named `hcc` (not `thames-river-conditions`).

## Secrets

Managed via Modal's secret store:

| Modal secret name | Environment variable | Used by |
|-------------------|---------------------|---------|
| `MET-OFFICE` | `MET_OFFICE_API_KEY` | `cache_weather` |
| `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | `get_gpt_summary` |

## Error handling

The EA flood monitoring API occasionally returns empty responses. Both flow and level fetches in `cache_flow` are wrapped in try/except — on failure, the previous cached value is preserved. The water temperature scraper and weather fetch also have try/except guards.

## Dependency management

Dependencies are managed with `uv`. The `pyproject.toml` declares all dependencies including git sources via PEP 508 direct references (e.g., `ea-rivers @ git+https://...`). The `uv.lock` file pins exact versions.

The Modal container image installs dependencies via `pip_install_from_pyproject("pyproject.toml")`, which passes the PEP 508 specs directly to pip inside the container.
