# Sotkanet MCP Server

An MCP server that wraps Sotkanet, Finland's national statistics and indicator bank for population health and welfare. This server exposes 3,700+ health indicators (elderly care, mental health, vaccination, child welfare, mortality, social support, and more) across Finland's 23 wellbeing services counties, 19 regions, and 308 municipalities. Use this server to benchmark regions, understand health trends, and answer questions about Finnish public health and social welfare data — all backed by THL (Finnish Institute for Health and Welfare).

## Tools

| Tool | Description |
|------|-------------|
| `search_indicators` | Keyword search across 3,700+ indicators by title (cached, instant) |
| `browse_indicator_groups` | Browse indicators by data provider or thematic organization |
| `get_indicator_metadata` | Full description of an indicator: what it measures, year range, data source |
| `get_indicator_data` | Values for all regions in a category for a single year (capped at 25 rows) |
| `compare_regions` | Rank regions by value on any indicator; returns top N with summary stats |
| `get_trend` | Time series for one region across multiple years with year-over-year change |

## How It Works

1. **Search** — User asks about a health topic (e.g., "elderly care rates") → `search_indicators` finds matching indicators
2. **Inspect** — `get_indicator_metadata` returns available years, data source, and what the indicator measures
3. **Choose region scope** — Decide on region type: counties (23, default), regions (19), municipalities (308), or whole country
4. **Fetch or compare** — `get_indicator_data` for current values, `compare_regions` for rankings, `get_trend` for time series
5. **Results** — Formatted tables with region names, values, and summary statistics

## Quick Start

```bash
git clone https://github.com/SimonBerg255/sotkanet-mcp.git
cd sotkanet-mcp

python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt

uvicorn server:app --host 0.0.0.0 --port 8000
```

Server runs at `http://localhost:8000`. Health check at `/health`.

## API Details

- **Base URL:** `https://sotkanet.fi/rest/1.1/`
- **Protocol:** REST JSON, no pagination on data endpoints
- **Authentication:** None (public API)
- **Rate limits:** Not enforced on public access; be respectful (no hammering)
- **Response format:** JSON for all endpoints
- **License:** THL data is CC BY 4.0; Sotkanet itself is open

## Region Categories

The server defaults to **HYVINVOINTIALUE** (23 wellbeing services counties) for national coverage without municipality explosion. Other options:

- `HYVINVOINTIALUE` — Wellbeing services counties (23) — **recommended default**
- `MAAKUNTA` — Regions (19)
- `ERVA` — University hospital special responsibility areas (5)
- `MAA` — Whole country (1, region ID 658)
- `SAIRAANHOITOPIIRI` — Hospital districts (21)
- `KUNTA` — Municipalities (308) — data capped at 25 rows with warning

## Indicator Search Tips

All 3,700+ indicators are cached on startup and searched by title locally (no API call needed). Good search terms:

- Health: "hospital", "GP visits", "waiting times", "vaccination", "mortality"
- Elderly: "elderly care", "home care", "institutional care", "aged 75"
- Mental health: "depression", "mental health", "substance abuse", "psychiatric"
- Child welfare: "child welfare", "child protection", "foster care"
- Social: "unemployment", "income support", "poverty", "social benefit"

## Validation

Run the test suite to verify all tools against live Sotkanet API:

```bash
python3 test_tools.py
```

Tests cover:
- Cache warm-up (3,700+ indicators loaded)
- Context overflow guards (max 25 raw rows)
- Municipality capping (300 regions capped with warning)
- Ranked comparison output (top N with stats)
- Time series formatting
- Metadata fetching
- Response timing (< 30s)
- Multilingual search (Finnish, English, Swedish)

All 8 tests must pass before the server is ready.

## License

MIT
